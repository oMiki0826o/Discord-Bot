"""
bot/core/modules/registry.py

Modification():

- 管理 Module 註冊資訊。
- 管理 Module 載入狀態。
- 提供 Module 查詢功能。
- 保存 Module 載入錯誤資訊。

本檔只負責 Module 狀態與中繼資料管理，
不負責 Module 掃描、載入、卸載或 Discord Extension 操作。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ── Module 狀態 ──────────────────────

class ModuleStatus(str, Enum):
    """Module 執行狀態。"""

    DISCOVERED = "discovered"
    LOADED = "loaded"
    FAILED = "failed"
    DISABLED = "disabled"


# ── Module 資訊 ──────────────────────

@dataclass(slots=True)
class ModuleInfo:
    """單一 Module 的註冊資訊。"""

    name: str
    extension: str
    version: str = "0.1.0"
    dependencies: tuple[str, ...] = ()
    status: ModuleStatus = ModuleStatus.DISCOVERED
    error: str | None = None


# ── Module Registry ──────────────────────

class ModuleRegistry:
    """管理所有已發現 Module 的狀態。"""

    def __init__(self) -> None:
        self._modules: dict[str, ModuleInfo] = {}


    # ── 註冊 ──────────────────────

    def register(
        self,
        name: str,
        extension: str,
        version: str = "0.1.0",
        dependencies: tuple[str, ...] = (),
    ) -> ModuleInfo:
        """註冊 Module。"""

        if name in self._modules:
            raise ValueError(
                f"Module 已存在：{name}"
            )

        module = ModuleInfo(
            name=name,
            extension=extension,
            version=version,
            dependencies=dependencies,
        )

        self._modules[name] = module

        return module


    # ── 狀態 ──────────────────────

    def mark_loaded(
        self,
        name: str,
    ) -> None:
        """將 Module 標記為已載入。"""

        module = self.require(name)

        module.status = ModuleStatus.LOADED
        module.error = None


    def mark_failed(
        self,
        name: str,
        error: str,
    ) -> None:
        """將 Module 標記為載入失敗。"""

        module = self.require(name)

        module.status = ModuleStatus.FAILED
        module.error = error


    def mark_disabled(
        self,
        name: str,
    ) -> None:
        """將 Module 標記為停用。"""

        module = self.require(name)

        module.status = ModuleStatus.DISABLED
        module.error = None


    def mark_discovered(
        self,
        name: str,
    ) -> None:
        """將 Module 重設為已發現狀態。"""

        module = self.require(name)

        module.status = ModuleStatus.DISCOVERED
        module.error = None


    # ── 查詢 ──────────────────────

    def get(
        self,
        name: str,
    ) -> ModuleInfo | None:
        """取得指定 Module。"""

        return self._modules.get(name)


    def require(
        self,
        name: str,
    ) -> ModuleInfo:
        """取得指定 Module，不存在時拋出錯誤。"""

        module = self.get(name)

        if module is None:
            raise KeyError(
                f"找不到 Module：{name}"
            )

        return module


    def all(self) -> tuple[ModuleInfo, ...]:
        """取得所有 Module。"""

        return tuple(
            self._modules.values()
        )


    def loaded(self) -> tuple[ModuleInfo, ...]:
        """取得所有已載入 Module。"""

        return tuple(
            module
            for module in self._modules.values()
            if module.status is ModuleStatus.LOADED
        )


    def failed(self) -> tuple[ModuleInfo, ...]:
        """取得所有載入失敗 Module。"""

        return tuple(
            module
            for module in self._modules.values()
            if module.status is ModuleStatus.FAILED
        )


    # ── Registry ──────────────────────

    def clear(self) -> None:
        """清除所有 Module 註冊資訊。"""

        self._modules.clear()
