"""
bot/core/modules/loader.py

Modification():

- 掃描並發現可載入的 Module。
- 管理 Discord Extension 載入。
- 管理 Discord Extension 卸載。
- 管理 Discord Extension 批次卸載。
- 管理 Discord Extension 重新載入。
- 將 Module 執行狀態同步至 Module Registry。
- 記錄 Module 生命週期錯誤。

本檔負責 Module 的發現與生命週期操作，
不負責 Module 業務邏輯或 Settings 內容管理。
"""

from __future__ import annotations

import logging
import asyncio
import ast
from pathlib import Path

from discord.ext import commands

from bot.core.modules.registry import (
    ModuleInfo,
    ModuleRegistry,
    ModuleStatus,
)
from bot.core.settings.manager import SettingsManager, settings
from bot.core.settings.schema import SettingRule


logger = logging.getLogger(
    "bot.modules.loader"
)

MODULE_CLEANUP_TIMEOUT = 10.0


# ── Module Loader ──────────────────────

class ModuleLoader:
    """管理 Bot 功能 Module 的發現與生命週期。"""

    def __init__(
        self,
        bot: commands.Bot,
        modules_dir: Path,
        modules_package: str = "bot.mod",
        settings_manager: SettingsManager = settings,
    ) -> None:
        self.bot = bot
        self.modules_dir = modules_dir
        self.modules_package = modules_package
        self.settings = settings_manager
        self.registry = ModuleRegistry()
        self._locks: dict[str, asyncio.Lock] = {}
        self.settings.register(
            "modules",
            {"disabled": [], "required": ["basic", "system"]},
            {
                "disabled": SettingRule(list, validator=lambda values: all(isinstance(value, str) and value for value in values), description="內容必須是非空 Module 名稱字串"),
                "required": SettingRule(list, validator=lambda values: all(isinstance(value, str) and value for value in values), description="內容必須是非空 Module 名稱字串"),
            },
        )

    def _lock_for(self, name: str) -> asyncio.Lock:
        return self._locks.setdefault(name, asyncio.Lock())

    def _disabled_names(self) -> set[str]:
        values = self.settings.get("modules.disabled", [])
        return {name for name in values if isinstance(name, str)}

    def _required_names(self) -> set[str]:
        values = self.settings.get("modules.required", [])
        return {name for name in values if isinstance(name, str)}

    # ── Module 發現 ──────────────────────

    def discover(
        self,
    ) -> tuple[ModuleInfo, ...]:
        """
        掃描 Module 根目錄。

        只有包含 extension.py 的資料夾
        才會被視為可載入 Module。
        """

        if not self.modules_dir.exists():
            logger.warning(
                "Module 目錄不存在：%s",
                self.modules_dir,
            )
            return ()

        for directory in sorted(
            self.modules_dir.iterdir(),
            key=lambda path: path.name,
        ):
            if not directory.is_dir():
                continue

            if directory.name.startswith(
                (".", "_")
            ):
                continue

            if not directory.name.isidentifier():
                logger.warning("忽略不合法 Module 名稱：%s", directory.name)
                continue

            extension_file = (
                directory / "extension.py"
            )

            if not extension_file.is_file():
                continue

            name = directory.name

            extension = (
                f"{self.modules_package}."
                f"{name}.extension"
            )

            if self.registry.get(name) is not None:
                continue

            self.registry.register(
                name=name,
                extension=extension,
                version=self._metadata(extension_file, "MODULE_VERSION", "0.1.0"),
                dependencies=self._metadata(
                    extension_file,
                    "MODULE_DEPENDENCIES",
                    (),
                ),
            )

            if name in self._disabled_names():
                self.registry.mark_disabled(name)

            logger.debug(
                "發現 Module：%s (%s)",
                name,
                extension,
            )

        return self.registry.all()

    @staticmethod
    def _metadata(
        extension_file: Path,
        key: str,
        default: object,
    ) -> object:
        """讀取 extension 的靜態 metadata，不執行 Module 程式碼。"""

        try:
            tree = ast.parse(extension_file.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as exc:
            logger.warning("Module metadata 讀取失敗：%s (%s)", extension_file, exc)
            return default

        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if not any(isinstance(target, ast.Name) and target.id == key for target in node.targets):
                continue
            try:
                value = ast.literal_eval(node.value)
            except (ValueError, TypeError, SyntaxError):
                return default
            if key == "MODULE_DEPENDENCIES":
                if isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
                    return tuple(value)
                return default
            return value if isinstance(value, str) else default
        return default

    # ── Module 依賴 ──────────────────────

    def _dependency_order(self) -> tuple[str, ...]:
        """驗證依賴圖並回傳依賴優先的拓樸排序。"""

        modules = {module.name: module for module in self.registry.all()}
        state: dict[str, int] = {}
        order: list[str] = []
        stack: list[str] = []

        def visit(name: str) -> None:
            status = state.get(name, 0)
            if status == 2:
                return
            if status == 1:
                start = stack.index(name)
                cycle = stack[start:] + [name]
                raise RuntimeError(
                    "偵測到 Module 循環依賴：" + " -> ".join(cycle)
                )

            module = modules.get(name)
            if module is None:
                raise RuntimeError(f"找不到 Module：{name}")

            state[name] = 1
            stack.append(name)

            for dependency in module.dependencies:
                if dependency == name:
                    raise RuntimeError(f"Module 不可依賴自身：{name}")
                if dependency not in modules:
                    raise RuntimeError(
                        f"Module {name} 缺少必要依賴：{dependency}"
                    )
                visit(dependency)

            stack.pop()
            state[name] = 2
            order.append(name)

        for name in sorted(modules):
            visit(name)

        return tuple(order)

    def _loaded_dependents(self, name: str) -> tuple[str, ...]:
        """取得目前已載入且直接依賴指定 Module 的模組。"""

        return tuple(
            module.name
            for module in self.registry.all()
            if name in module.dependencies
            and module.extension in self.bot.extensions
        )

    async def _load_with_dependencies(
        self,
        name: str,
        loading: set[str] | None = None,
    ) -> bool:
        """先載入依賴，再載入指定 Module。"""

        module = self.registry.require(name)
        loading = loading or set()

        if name in loading:
            logger.error("偵測到 Module 循環依賴：%s", name)
            return False

        loading.add(name)
        try:
            for dependency_name in module.dependencies:
                dependency = self.registry.get(dependency_name)
                if dependency is None:
                    error = f"缺少必要依賴：{dependency_name}"
                    self.registry.mark_failed(name, error)
                    logger.error("Module %s %s", name, error)
                    return False

                if dependency_name in self._disabled_names():
                    error = f"必要依賴已停用：{dependency_name}"
                    self.registry.mark_failed(name, error)
                    logger.error("Module %s %s", name, error)
                    return False

                if dependency.extension not in self.bot.extensions:
                    if not await self._load_with_dependencies(dependency_name, loading):
                        error = f"必要依賴載入失敗：{dependency_name}"
                        self.registry.mark_failed(name, error)
                        logger.error("Module %s %s", name, error)
                        return False

            return await self._load(name)
        finally:
            loading.discard(name)

    # ── Module 載入 ──────────────────────

    async def load(
        self,
        name: str,
    ) -> bool:
        """載入指定 Module。"""

        async with self._lock_for(name):
            return await self._load_with_dependencies(name)

    async def _load(self, name: str) -> bool:
        module = self.registry.require(name)

        if name in self._disabled_names():
            self.registry.mark_disabled(name)
            logger.info("Module 已停用，略過載入：%s", name)
            return False

        try:
            await self.bot.load_extension(
                module.extension
            )

        except commands.ExtensionAlreadyLoaded:
            self.registry.mark_loaded(
                name
            )

            logger.debug(
                "Module 已載入：%s",
                name,
            )

            return True

        except Exception as exc:
            self.registry.mark_failed(
                name,
                f"{type(exc).__name__}: {exc}",
            )

            logger.exception(
                "Module 載入失敗：%s",
                name,
            )

            return False

        self.registry.mark_loaded(
            name
        )

        logger.info(
            "Module 載入完成：%s",
            name,
        )

        return True

    async def load_all(
        self,
    ) -> None:
        """載入所有已發現 Module。"""

        self.discover()

        try:
            order = self._dependency_order()
        except RuntimeError as exc:
            logger.error("Module 依賴驗證失敗：%s", exc)
            raise

        failures: list[str] = []
        for name in order:
            module = self.registry.require(name)
            if module.status is ModuleStatus.DISABLED:
                continue
            if not await self.load(name):
                failures.append(name)

        required_failures = sorted(set(failures) & self._required_names())
        if required_failures:
            raise RuntimeError(
                "必要 Module 載入失敗：" + ", ".join(required_failures)
            )

    # ── Module 卸載 ──────────────────────

    async def unload(
        self,
        name: str,
    ) -> bool:
        """卸載指定 Module。"""

        async with self._lock_for(name):
            return await self._unload(name)

    async def _unload(self, name: str) -> bool:
        module = self.registry.require(name)

        dependents = self._loaded_dependents(name)
        if dependents:
            logger.error(
                "Module 無法卸載：%s；仍被以下 Module 使用：%s",
                name,
                ", ".join(dependents),
            )
            return False

        try:
            await self.bot.unload_extension(
                module.extension
            )

        except commands.ExtensionNotLoaded:
            self.registry.mark_discovered(
                name
            )

            logger.debug(
                "Module 尚未載入：%s",
                name,
            )

            return True

        except Exception as exc:
            self.registry.mark_failed(
                name,
                f"{type(exc).__name__}: {exc}",
            )

            logger.exception(
                "Module 卸載失敗：%s",
                name,
            )

            return False

        self.registry.mark_discovered(
            name
        )

        logger.info(
            "Module 卸載完成：%s",
            name,
        )

        return True

    async def unload_all(
        self,
    ) -> bool:
        """依載入反序卸載所有目前已載入的 Module。"""

        success = True

        try:
            names = tuple(reversed(self._dependency_order()))
        except RuntimeError as exc:
            logger.error("Module 依賴驗證失敗：%s", exc)
            return False

        modules = tuple(self.registry.require(name) for name in names)

        for module in modules:
            if module.extension not in self.bot.extensions:
                continue

            try:
                unloaded = await asyncio.wait_for(
                    self.unload(module.name),
                    timeout=MODULE_CLEANUP_TIMEOUT,
                )
            except asyncio.TimeoutError:
                logger.error("Module Cleanup 逾時：%s", module.name)
                success = False
                continue

            if not unloaded:
                success = False

        return success

    # ── Module 重載 ──────────────────────

    async def reload(
        self,
        name: str,
    ) -> bool:
        """重新載入指定 Module。"""

        async with self._lock_for(name):
            return await self._reload(name)

    async def _reload(self, name: str) -> bool:
        module = self.registry.require(name)

        if name in self._disabled_names():
            self.registry.mark_disabled(name)
            return False

        try:
            await self.bot.reload_extension(
                module.extension
            )

        except commands.ExtensionNotLoaded:
            return await self._load_with_dependencies(name)

        except Exception as exc:
            self.registry.mark_failed(
                name,
                f"{type(exc).__name__}: {exc}",
            )

            logger.exception(
                "Module 重載失敗：%s",
                name,
            )

            return False

        self.registry.mark_loaded(
            name
        )

        logger.info(
            "Module 重載完成：%s",
            name,
        )

        return True

    def rescan(self) -> tuple[ModuleInfo, ...]:
        """重新掃描 Module 目錄並註冊新 Module。"""

        return self.discover()

    def health_summary(self) -> tuple[dict[str, object], ...]:
        """回傳適合 Owner 維運檢查的模組摘要。"""

        return tuple(
            {
                "name": module.name,
                "version": module.version,
                "dependencies": module.dependencies,
                "status": module.status.value,
                "error": module.error,
            }
            for module in self.registry.all()
        )

    async def disable(self, name: str) -> bool:
        """持久化停用 Module，並在必要時卸載它。"""

        async with self._lock_for(name):
            module = self.registry.require(name)
            if module.extension in self.bot.extensions:
                if not await self._unload(name):
                    return False
            disabled = self._disabled_names()
            disabled.add(name)
            self.settings.set("modules.disabled", sorted(disabled))
            self.registry.mark_disabled(name)
            return True

    async def enable(self, name: str) -> bool:
        """取消持久化停用，並載入 Module。"""

        async with self._lock_for(name):
            self.registry.require(name)
            disabled = self._disabled_names()
            disabled.discard(name)
            self.settings.set("modules.disabled", sorted(disabled))
            self.registry.mark_discovered(name)
            return await self._load_with_dependencies(name)
