"""
bot/mod/ai/history/lexical.py

Modification():

- 將 History 文字正規化成穩定的 FTS 索引內容。
- 加入 CJK bigram，不依賴外部中文斷詞器。

本檔不執行資料庫查詢。
"""

from __future__ import annotations

import re


_CJK_RANGE = r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_LEXEME_PATTERN = re.compile(
    rf"[{_CJK_RANGE}]+|[^\W_]+",
    re.UNICODE,
)
_CJK_PATTERN = re.compile(rf"^[{_CJK_RANGE}]+$")


def normalize_lexical_document(text: str) -> str:
    """產生可重現的索引文字；允許沒有可索引 token。"""

    if not isinstance(text, str):
        raise ValueError("text 必須是字串")

    folded = text.casefold()
    tokens: list[str] = []
    for lexeme in _LEXEME_PATTERN.findall(folded):
        if _CJK_PATTERN.fullmatch(lexeme) is None:
            tokens.append(lexeme)
        elif len(lexeme) == 1:
            tokens.append(lexeme)
        else:
            tokens.extend(
                lexeme[index:index + 2]
                for index in range(len(lexeme) - 1)
            )
    return " ".join(tokens)


def normalize_lexical_query(text: str) -> str:
    """產生 FTS MATCH 輸入，拒絕沒有 token 的查詢。"""

    normalized = normalize_lexical_document(text)
    if not normalized:
        raise ValueError("query 不得空白或只含無法索引的字元")
    return normalized
