"""教职工基本信息表（ODS_JZGJBSJ）填报约束。

规则来自《数据标准规范》表 6-4：必填、条件必填、字典取值、身份证校验，
以及学历与学位的提示性校验。
"""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

TITLE_RANKS = (
    "教授",
    "副教授",
    "讲师",
    "助教",
    "其他正高级",
    "其他副高级",
    "其他中级",
    "其他初级",
    "未评级",
)

_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECKS = "10X98765432"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DEGREE_HINT = {
    "博士研究生": {"博士"},
    "硕士研究生": {"硕士", "学士"},
    "本科": {"学士"},
}


class StaffWrite(BaseModel):
    YXBMCMC: str = Field(max_length=60)
    JGH: str = Field(max_length=20)
    JSXM: str = Field(max_length=36)
    XB: str = Field(max_length=1)
    SFZJH: str = Field(max_length=18)
    CSRQ: str = Field(max_length=10)
    ZZMM: str = Field(max_length=20)
    MZ: str = Field(max_length=20)
    XL: str = Field(max_length=20)
    BYXXGJDQ: str = Field(max_length=60)
    BYXXMC: str = Field(max_length=100)
    XW: str = Field(max_length=10)
    RYLB: str = Field(max_length=20)
    SRZW: str = Field(max_length=60)
    ZYLY: str = Field(max_length=20)
    ZYTC: str = Field(max_length=100)
    SFYGXJSZGZS: str = Field(max_length=1)
    GXJSZGZFZDW: str | None = Field(default=None, max_length=60)
    GXJSZGZHQRQ: str | None = Field(default=None, max_length=7)
    ZYJSZWDJ: str | None = Field(default=None, max_length=20)
    ZYJSZWMC: str | None = Field(default=None, max_length=60)
    ZYJSZWFZDW: str | None = Field(default=None, max_length=60)
    ZYJSZWHQRQ: str | None = Field(default=None, max_length=7)
    ZYGGZSDJ: str | None = Field(default=None, max_length=10)
    ZYGGZSMC: str | None = Field(default=None, max_length=100)
    ZYGGZSFZDW: str | None = Field(default=None, max_length=60)
    ZYGGZSHQRQ: str | None = Field(default=None, max_length=7)
    SFZYJS: str = Field(max_length=1)
    XZSSZYMC: str | None = Field(default=None, max_length=60)
    XZSSZYDM: str | None = Field(default=None, max_length=6)
    XZSSZYCC: str | None = Field(default=None, max_length=10)
    XZSSZYDL: str | None = Field(default=None, max_length=40)
    SFGGKJS: str = Field(max_length=1)
    SRGGKC: str | None = Field(default=None, max_length=50)
    SFSZXJS: str = Field(max_length=10)
    JXMS: str = Field(max_length=10)
    SFZZSZKJS: str = Field(max_length=1)
    SFJZSZKJS: str = Field(max_length=1)
    SFZZFDY: str = Field(max_length=1)
    SFJZFDY: str = Field(max_length=1)
    SFZZXLJKJS: str = Field(max_length=1)
    SFJZXLJKJS: str = Field(max_length=1)
    SFZYDTR: str = Field(max_length=10)
    ZYDTNX: int | None = Field(default=None, ge=0, le=99)
    SFZYQFZR: str = Field(max_length=10)
    ZYQFZRNX: int | None = Field(default=None, ge=0, le=99)
    CZHYQYGZNX: Decimal = Field(ge=0, le=Decimal("999.9"))


def blank(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _choice(value: str, label: str, allowed: set[str], errors: list[str]) -> str:
    text = value.strip()
    if not text:
        errors.append(f"{label}不能为空")
    elif text not in allowed:
        errors.append(f"{label}不在数据字典取值范围内")
    return text


def _text(value: str, label: str, errors: list[str]) -> str:
    text = value.strip()
    if not text:
        errors.append(f"{label}不能为空")
    return text


def _date(value: str, label: str, errors: list[str]) -> str:
    text = value.strip()
    if not _DATE.fullmatch(text):
        errors.append(f"{label}须为 YYYY-MM-DD")
        return text
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        errors.append(f"{label}不是有效日期")
    return text


def _month(value: str | None, label: str, errors: list[str]) -> str | None:
    text = blank(value)
    if text is not None and not _MONTH.fullmatch(text):
        errors.append(f"{label}须为 YYYY-MM")
    return text


def id_card_birth_gender(sfzjh: str) -> tuple[str | None, str | None, list[str]]:
    """返回（出生日期，性别代码 1男 2女，错误）。"""
    text = sfzjh.strip().upper()
    if re.fullmatch(r"\d{17}[\dX]", text):
        total = sum(int(text[index]) * _ID_WEIGHTS[index] for index in range(17))
        if _ID_CHECKS[total % 11] != text[-1]:
            return None, None, ["身份证号格式或校验位错误"]
        raw = text[6:14]
        gender_digit = int(text[16])
    elif re.fullmatch(r"\d{15}", text):
        raw = "19" + text[6:12]
        gender_digit = int(text[14])
    else:
        return None, None, ["身份证号格式或校验位错误"]
    birth = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    try:
        datetime.strptime(birth, "%Y-%m-%d")
    except ValueError:
        return None, None, ["身份证号格式或校验位错误"]
    return birth, "1" if gender_digit % 2 else "2", []


def normalize_staff(
    payload: StaffWrite, options: dict[str, set[str]], departments: set[str]
) -> tuple[dict[str, object], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    data = payload.model_dump()

    department = _text(payload.YXBMCMC, "院系部名称", errors)
    if department and department not in departments:
        errors.append("院系部名称不在部门名录中")
    data["YXBMCMC"] = department
    data["JGH"] = _text(payload.JGH, "教工号", errors)
    data["JSXM"] = _text(payload.JSXM, "姓名", errors)
    data["XB"] = _choice(payload.XB, "性别", options["D55"], errors)
    data["SFZJH"] = payload.SFZJH.strip().upper()
    birth, gender, id_errors = id_card_birth_gender(data["SFZJH"])
    errors.extend(id_errors)
    data["CSRQ"] = _date(payload.CSRQ, "出生日期", errors)
    if birth and data["CSRQ"] != birth:
        errors.append("出生日期与身份证号不一致")
    if gender and data["XB"] == gender or not gender:
        pass
    elif data["XB"] in options["D55"]:
        errors.append("性别与身份证号不一致")

    data["ZZMM"] = _choice(payload.ZZMM, "政治面貌", options["D21"], errors)
    data["MZ"] = _choice(payload.MZ, "民族", options["D22"], errors)
    data["XL"] = _choice(payload.XL, "学历", options["D23"], errors)
    data["BYXXGJDQ"] = _choice(
        payload.BYXXGJDQ, "最高学历毕业学校所在国家（地区）", options["D63"], errors
    )
    data["BYXXMC"] = _text(payload.BYXXMC, "最高学历毕业学校名称", errors)
    data["XW"] = _choice(payload.XW, "学位", options["D24"], errors)
    expected = _DEGREE_HINT.get(data["XL"])
    if expected and data["XW"] not in expected:
        warnings.append("学历与学位不匹配")

    data["RYLB"] = _choice(payload.RYLB, "人员类别", options["D19"], errors)
    data["SRZW"] = _text(payload.SRZW, "所任职务", errors)
    data["ZYLY"] = _choice(payload.ZYLY, "专业领域", options["D25"], errors)
    data["ZYTC"] = _text(payload.ZYTC, "专业特长", errors)

    has_cert = _choice(payload.SFYGXJSZGZS, "是否拥有高校教师资格证书", options["D28"], errors)
    issuer = blank(payload.GXJSZGZFZDW)
    cert_date = _month(payload.GXJSZGZHQRQ, "高校教师资格证书获取日期", errors)
    if has_cert == "1" and (issuer is None or cert_date is None):
        errors.append("有教师资格证须填写发证单位和日期")
    if has_cert != "1":
        issuer, cert_date = None, None
    data["SFYGXJSZGZS"] = has_cert
    data["GXJSZGZFZDW"] = issuer
    data["GXJSZGZHQRQ"] = cert_date

    rank = blank(payload.ZYJSZWDJ)
    title_name = blank(payload.ZYJSZWMC)
    title_issuer = blank(payload.ZYJSZWFZDW)
    title_date = _month(payload.ZYJSZWHQRQ, "专业技术职务获取日期", errors)
    title_parts = (rank, title_name, title_issuer, title_date)
    if any(title_parts) and not all(title_parts):
        errors.append("有专业技术职务须填写等级、名称、发证单位和获取日期")
    if rank is not None and rank not in TITLE_RANKS:
        errors.append("专业技术职务等级不在取值范围内")
    data["ZYJSZWDJ"] = rank
    data["ZYJSZWMC"] = title_name
    data["ZYJSZWFZDW"] = title_issuer
    data["ZYJSZWHQRQ"] = title_date

    cert_rank = blank(payload.ZYGGZSDJ)
    cert_name = blank(payload.ZYGGZSMC)
    cert_issuer = blank(payload.ZYGGZSFZDW)
    cert_got = _month(payload.ZYGGZSHQRQ, "职业资格证书获取日期", errors)
    if cert_rank is not None and cert_rank not in options["D27"]:
        errors.append("职业资格证书等级不在数据字典取值范围内")
    if cert_rank == "无" and any((cert_name, cert_issuer, cert_got)):
        errors.append("职业资格证书等级为无时不应填写证书名称、发证单位或获取日期")
    elif cert_rank not in {None, "无"} and not all((cert_name, cert_issuer, cert_got)):
        errors.append("有职业资格证书须填写等级、名称、发证单位和获取日期")
    elif cert_rank is None and any((cert_name, cert_issuer, cert_got)):
        errors.append("有职业资格证书须填写等级、名称、发证单位和获取日期")
    data["ZYGGZSDJ"] = cert_rank
    data["ZYGGZSMC"] = cert_name
    data["ZYGGZSFZDW"] = cert_issuer
    data["ZYGGZSHQRQ"] = cert_got

    professional = _choice(payload.SFZYJS, "是否专业教师", options["D28"], errors)
    major_name = blank(payload.XZSSZYMC)
    major_code = blank(payload.XZSSZYDM)
    major_level = blank(payload.XZSSZYCC)
    major_class = blank(payload.XZSSZYDL)
    if professional == "1":
        if not all((major_name, major_code, major_level, major_class)):
            errors.append("专业教师须填写所属专业")
        elif major_level not in options["D01"]:
            errors.append("行政所属专业层次不在数据字典取值范围内")
    else:
        major_name = major_code = major_level = major_class = None
    data["SFZYJS"] = professional
    data["XZSSZYMC"] = major_name
    data["XZSSZYDM"] = major_code
    data["XZSSZYCC"] = major_level
    data["XZSSZYDL"] = major_class

    public_teacher = _choice(payload.SFGGKJS, "是否公共课教师", options["D28"], errors)
    public_course = blank(payload.SRGGKC)
    if public_teacher == "1":
        if public_course is None:
            errors.append("公共课教师须填写所任课程")
        elif public_course not in options["D14"]:
            errors.append("所任公共课程不在数据字典取值范围内")
    else:
        public_course = None
    data["SFGGKJS"] = public_teacher
    data["SRGGKC"] = public_course

    data["SFSZXJS"] = _choice(payload.SFSZXJS, "是否为双师型教师", options["D29"], errors)
    data["JXMS"] = _choice(payload.JXMS, "教学名师", options["D30"], errors)
    for key, label, code in (
        ("SFZZSZKJS", "是否专职思政课教师", "D28"),
        ("SFJZSZKJS", "是否兼职思政课教师", "D28"),
        ("SFZZFDY", "是否专职辅导员", "D28"),
        ("SFJZFDY", "是否兼职辅导员", "D28"),
        ("SFZZXLJKJS", "是否专职心理健康教师", "D28"),
        ("SFJZXLJKJS", "是否兼职心理健康教师", "D28"),
    ):
        data[key] = _choice(str(getattr(payload, key)), label, options[code], errors)

    leader = _choice(payload.SFZYDTR, "是否专业带头人", options["D31"], errors)
    leader_years = payload.ZYDTNX
    if leader == "否":
        if leader_years not in {None, 0}:
            errors.append("专业带头人年限与标志不匹配")
        leader_years = 0
    elif leader_years is None:
        errors.append("担任专业带头人年限不能为空")
    data["SFZYDTR"] = leader
    data["ZYDTNX"] = leader_years

    group_leader = _choice(payload.SFZYQFZR, "是否专业（群）负责人", options["D32"], errors)
    group_years = payload.ZYQFZRNX
    if group_leader == "否":
        if group_years not in {None, 0}:
            errors.append("专业（群）负责人年限与标志不匹配")
        group_years = 0
    elif group_years is None:
        errors.append("担任专业（群）负责人年限不能为空")
    data["SFZYQFZR"] = group_leader
    data["ZYQFZRNX"] = group_years

    years = payload.CZHYQYGZNX
    if years != years.quantize(Decimal("0.1")):
        errors.append("曾在行业企业工作年限须保留 1 位小数")
    data["CZHYQYGZNX"] = years.quantize(Decimal("0.1"))
    return data, errors, warnings
