from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class DictOption(BaseModel):
    value: str
    label: str


class StaffFormMeta(BaseModel):
    departments: list[str]
    dicts: dict[str, list[DictOption]]
    title_ranks: list[str]
    scope: str
    account: str
    name: str
    department_name: str | None
    can_submit: bool


class StaffMemberRead(ORMModel):
    ZJSJWYXBS: str
    XXDM: str
    YXBMCMC: str
    JGH: str
    JSXM: str
    XB: str
    SFZJH: str
    CSRQ: str
    ZZMM: str
    MZ: str
    XL: str
    BYXXGJDQ: str
    BYXXMC: str
    XW: str
    RYLB: str
    SRZW: str
    ZYLY: str
    ZYTC: str
    SFYGXJSZGZS: str
    GXJSZGZFZDW: str | None
    GXJSZGZHQRQ: str | None
    ZYJSZWDJ: str | None
    ZYJSZWMC: str | None
    ZYJSZWFZDW: str | None
    ZYJSZWHQRQ: str | None
    ZYGGZSDJ: str | None
    ZYGGZSMC: str | None
    ZYGGZSFZDW: str | None
    ZYGGZSHQRQ: str | None
    SFZYJS: str
    XZSSZYMC: str | None
    XZSSZYDM: str | None
    XZSSZYCC: str | None
    XZSSZYDL: str | None
    SFGGKJS: str
    SRGGKC: str | None
    SFSZXJS: str
    JXMS: str
    SFZZSZKJS: str
    SFJZSZKJS: str
    SFZZFDY: str
    SFJZFDY: str
    SFZZXLJKJS: str
    SFJZXLJKJS: str
    SFZYDTR: str
    ZYDTNX: int | None
    SFZYQFZR: str
    ZYQFZRNX: int | None
    CZHYQYGZNX: Decimal
    SJCJSJ: str
    TBR: str | None
    warnings: list[str] = Field(default_factory=list)


class StaffListItem(BaseModel):
    ZJSJWYXBS: str
    JGH: str
    JSXM: str
    XB: str
    YXBMCMC: str
    RYLB: str
    XL: str
    SFZJH: str
    SJCJSJ: str
