"""教务处数据域：专业、课程、授课、在校生。

填写人是教务处审核员或信息中心。教务处提交后直接进入信息中心审核。
业务主键与 ODS 唯一约束一致。课程、授课、在校生在保存时核对已发布的关联记录。
"""

import re
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.datasets.spec import DatasetSpec, FieldSpec, Publish, Relate
from app.datasets.validate import Hook, check_fields
from app.models.academic import Course, Major, TeachingAssignment
from app.models.base import Base
from app.models.common import data_collection_timestamp
from app.models.records import BizRecord
from app.models.staff import StaffMember
from app.models.students import Student
from app.models.system import User

ACADEMIC = "academic"
REVIEW = "BM07"
_Model = type[Base]
_TERM = re.compile(r"^\d{4}-\d{4}-[12]学期$")
_DECIMALS = {"BCSKSS", "XSKSS", "JXGZL", "RXZF"}
_INTEGERS = {"KZZXS", "SJJXKSS"}


def _field(
    code: str,
    label: str,
    kind: str,
    group: str,
    *,
    required: bool = False,
    max_length: int | None = None,
    dict_code: str | None = None,
    visible_when: str | None = None,
    sensitive: bool = False,
    default: str | None = None,
) -> FieldSpec:
    return FieldSpec(
        code=code,
        label=label,
        kind=kind,
        group=group,
        required=required,
        max_length=max_length,
        dict_code=dict_code,
        visible_when=visible_when,
        sensitive=sensitive,
        default=default,
    )


def _flag(code: str, label: str, group: str) -> FieldSpec:
    return _field(code, label, "select", group, required=True, dict_code="D28", default="0")


def _department(code: str, label: str, group: str) -> FieldSpec:
    return _field(
        code, label, "select", group, required=True, dict_code="departments", max_length=60
    )


def _term(code: str, label: str) -> Hook:
    def hook(data: dict[str, object], errors: list[str]) -> None:
        value = data.get(code)
        if isinstance(value, str) and _TERM.fullmatch(value) is None:
            errors.append(f"{label}须形如 2025-2026-1学期")

    return hook


def _chain(*hooks: Hook) -> Hook:
    def hook(data: dict[str, object], errors: list[str]) -> None:
        for item in hooks:
            item(data, errors)

    return hook


def _major_rules(data: dict[str, object], errors: list[str]) -> None:
    code = data.get("ZYDM")
    if isinstance(code, str) and re.fullmatch(r"\d{6}", code) is None:
        errors.append("专业代码须为 6 位数字")
    approved = data.get("PZSZNY")
    enrolled = data.get("SCZSNY")
    if isinstance(approved, str) and isinstance(enrolled, str) and approved > enrolled:
        errors.append("首次招生日期不能早于批准设置日期")


def _course_rules(data: dict[str, object], errors: list[str]) -> None:
    total = data.get("KZZXS")
    practice = data.get("SJJXKSS")
    if isinstance(total, int) and total <= 0:
        errors.append("课程总学时须大于 0")
    if isinstance(total, int) and isinstance(practice, int) and not 0 <= practice <= total:
        errors.append("实践教学学时须在 0 和总学时之间")
    if data.get("KCSXM") == "公共基础课程" and not data.get("GGKC"):
        errors.append("课程属性为公共基础课程时须选择公共基础课程类别")
    if data.get("KCSXM") == "专业（技能）课程" and not data.get("ZYKC"):
        errors.append("课程属性为专业课程时须选择专业课程类别")


def _teaching_rules(data: dict[str, object], errors: list[str]) -> None:
    total = data.get("BCSKSS")
    online = data.get("XSKSS")
    workload = data.get("JXGZL")
    if isinstance(total, Decimal) and total <= 0:
        errors.append("本场所教学课时数须大于 0")
    if isinstance(workload, Decimal) and workload <= 0:
        errors.append("教师教学工作量须大于 0")
    if isinstance(total, Decimal) and isinstance(online, Decimal) and not 0 <= online <= total:
        errors.append("线上教学课时数须在 0 和本场所课时之间")


def _typed(data: dict[str, object]) -> dict[str, object]:
    converted: dict[str, object] = {}
    for key, value in data.items():
        if key in _DECIMALS and value is not None:
            converted[key] = Decimal(str(value))
        elif key in _INTEGERS and value is not None:
            converted[key] = int(str(value))
        else:
            converted[key] = value
    return converted


def _publisher(model: _Model, unique: tuple[str, ...], *, name_field: str | None = None) -> Publish:
    async def publish(
        session: AsyncSession, record: BizRecord, data: dict[str, object], user: User
    ) -> str:
        converted = _typed(data)
        if name_field is not None:
            named = select(model).where(getattr(model, name_field) == converted[name_field])
            if record.ods_id:
                named = named.where(model.ZJSJWYXBS != record.ods_id)  # type: ignore[attr-defined]
            if await session.scalar(named) is not None:
                raise HTTPException(status.HTTP_409_CONFLICT, detail="已发布数据中存在相同名称")
        clauses = [getattr(model, name) == converted[name] for name in unique]
        query = select(model).where(*clauses)
        if record.ods_id:
            query = query.where(model.ZJSJWYXBS != record.ods_id)  # type: ignore[attr-defined]
        if await session.scalar(query) is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="已发布数据中存在相同业务主键")
        row = await session.get(model, record.ods_id) if record.ods_id else None
        if row is None:
            row = model()
            row.XXDM = settings.school_code  # type: ignore[attr-defined]
            session.add(row)
        for key, value in converted.items():
            setattr(row, key, value)
        row.SJCJSJ = data_collection_timestamp()  # type: ignore[attr-defined]
        row.TBR = user.name[:36]  # type: ignore[attr-defined]
        await session.flush()
        identifier = row.ZJSJWYXBS  # type: ignore[attr-defined]
        if not isinstance(identifier, str):
            raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail="发布失败")
        return identifier

    return publish


async def _require_major(session: AsyncSession, data: dict[str, object]) -> Major:
    row = await session.scalar(select(Major).where(Major.ZYDM == data.get("ZYDM")))
    if row is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="专业代码尚未发布")
    if data.get("ZYMC") != row.ZYMC:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="专业名称与已发布专业不一致")
    return row


async def _course_links(session: AsyncSession, data: dict[str, object]) -> None:
    await _require_major(session, data)


async def _teaching_links(session: AsyncSession, data: dict[str, object]) -> None:
    course = await session.scalar(
        select(Course).where(
            Course.ZYDM == data.get("ZYDM"),
            Course.NJ == data.get("NJ"),
            Course.KCH == data.get("KCH"),
        )
    )
    if course is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="课程尚未发布")
    if data.get("KCMC") != course.KCMC:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="课程名称与已发布课程不一致")
    teacher = await session.scalar(select(StaffMember).where(StaffMember.JGH == data.get("JGH")))
    if teacher is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="授课教师工号尚未发布")
    if data.get("JSXM") != teacher.JSXM:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="授课教师姓名与教职工信息不一致")


async def _student_links(session: AsyncSession, data: dict[str, object]) -> None:
    await _require_major(session, data)


def _spec(
    *,
    code: str,
    name: str,
    business_key_fields: tuple[str, ...],
    department_field: str,
    list_fields: tuple[str, ...],
    groups: tuple[tuple[str, str | None], ...],
    fields: tuple[FieldSpec, ...],
    model: _Model,
    hook: Hook,
    relate: Relate | None = None,
    name_field: str | None = None,
) -> DatasetSpec:
    def validate(
        payload: dict[str, object], options: dict[str, set[str]], departments: set[str]
    ) -> tuple[dict[str, object], list[str]]:
        return check_fields(fields, payload, options, departments, hook)

    return DatasetSpec(
        code=code,
        name=name,
        category=ACADEMIC,
        review_department=REVIEW,
        business_key_fields=business_key_fields,
        owner_field=None,
        department_field=department_field,
        list_fields=list_fields,
        fields=fields,
        groups=groups,
        validate=validate,
        publish=_publisher(model, business_key_fields, name_field=name_field),
        relate=relate,
    )


def academic_datasets() -> tuple[DatasetSpec, ...]:
    return (_major(), _course(), _teaching(), _student())


def _major() -> DatasetSpec:
    group = "专业"
    focus = "重点专业"
    career = "产业与职业"
    return _spec(
        code="ODS_ZYSZSJ",
        name="专业设置",
        business_key_fields=("ZYDM",),
        department_field="ZYSSYXBMC",
        list_fields=("ZYDM", "ZYMC", "ZYCCM", "ZYSSYXBMC"),
        groups=(
            (group, "专业代码为 6 位数字。首次招生不能早于批准设置。"),
            (focus, "选择重点专业后须填写级别和类型。"),
            (career, None),
        ),
        fields=(
            _field("ZYMC", "专业名称", "text", group, required=True, max_length=60),
            _field("ZYDM", "专业代码", "text", group, required=True, max_length=6),
            _field("ZYCCM", "专业层次", "select", group, required=True, dict_code="D01"),
            _field("XZM", "学制", "select", group, required=True, dict_code="D02"),
            _field("ZYDLMC", "专业大类", "select", group, required=True, dict_code="D66"),
            _field("ZYFLMC", "专业类", "text", group, required=True, max_length=40),
            _field("PZSZNY", "批准设置日期", "month", group, required=True),
            _field("SCZSNY", "首次招生日期", "month", group, required=True),
            _department("ZYSSYXBMC", "专业所属院系部", group),
            # D01 中职业本科的取值为 "1"，只有职业本科授予学位
            _field(
                "SYXWLBM",
                "学位授予门类",
                "select",
                group,
                required=True,
                dict_code="D03",
                visible_when="ZYCCM",
            ),
            _flag("SFZDZY", "是否重点专业", focus),
            _field(
                "ZDZYJBM",
                "重点专业级别",
                "select",
                focus,
                required=True,
                dict_code="D04",
                visible_when="SFZDZY",
            ),
            _field(
                "ZDZYLXM",
                "重点专业类型",
                "select",
                focus,
                required=True,
                dict_code="D05",
                visible_when="SFZDZY",
            ),
            _field(
                "ZYPPCYQK",
                "专业匹配地方产业情况",
                "select",
                career,
                required=True,
                dict_code="D06",
            ),
            _field("CYMC", "产业名称", "text", career, max_length=200),
            _field("GNDW", "功能定位", "text", career, max_length=100),
            _field("ZYJYDLMC", "职业类别大类名称", "text", career, required=True, max_length=100),
            _field("ZYJYFLMC", "职业类别中类名称", "text", career, required=True, max_length=100),
            _field("ZYJYXLMC", "职业类别小类名称", "text", career, required=True, max_length=200),
        ),
        model=Major,
        hook=_major_rules,
        name_field="ZYMC",
    )


def _course() -> DatasetSpec:
    group = "课程"
    return _spec(
        code="ODS_KCJBSJ",
        name="课程基本数据",
        business_key_fields=("ZYDM", "NJ", "KCH"),
        department_field="KKDWMC",
        list_fields=("KCH", "KCMC", "ZYDM", "NJ", "KKDWMC"),
        groups=((group, "开课学期形如 2025-2026-1学期。实践教学学时不能超过总学时。"),),
        fields=(
            _field("ZYMC", "专业名称", "text", group, required=True, max_length=60),
            _field("ZYDM", "专业代码", "text", group, required=True, max_length=6),
            _field("ZYCCM", "专业层次", "select", group, required=True, dict_code="D01"),
            _field("XZM", "学制", "select", group, required=True, dict_code="D02"),
            _field("PYFSM", "培养方式", "select", group, required=True, dict_code="D07"),
            _field("JTXS", "具体形式", "select", group, dict_code="D08"),
            _field("SYLXM", "生源类型", "select", group, required=True, dict_code="D09"),
            _field("NJ", "年级", "select", group, required=True, dict_code="D11"),
            _field("KCMC", "课程名称", "text", group, required=True, max_length=60),
            _field("KCH", "课程代码", "text", group, required=True, max_length=20),
            _field("KCLXM", "课程类型", "select", group, required=True, dict_code="D12"),
            _field("KCSXM", "课程属性", "select", group, required=True, dict_code="D13"),
            _field("GGKC", "公共基础课程", "select", group, dict_code="D14"),
            _field("ZYKC", "专业课程", "select", group, dict_code="D15"),
            _field("KCXZM", "课程性质", "select", group, required=True, dict_code="D16"),
            _field("KKXQM", "开课学期", "text", group, required=True, max_length=20),
            _department("KKDWMC", "开课单位名称", group),
            _flag("SFXQHZKFKC", "是否校企合作开发课程", group),
            _field(
                "HZQYMC",
                "合作企业名称",
                "text",
                group,
                required=True,
                max_length=200,
                visible_when="SFXQHZKFKC",
            ),
            _field("ZXJPC", "在线精品课程", "select", group, required=True, dict_code="D18"),
            _flag("SFKZRTKC", "是否课证融通课程", group),
            _flag("SFWLJXKC", "是否网络教学课程", group),
            _field("KCSZSFK", "课程思政示范课", "select", group, required=True, dict_code="D18"),
            _field("KZZXS", "课程总学时", "number", group, required=True),
            _field("SJJXKSS", "实践教学学时", "number", group, required=True),
        ),
        model=Course,
        hook=_chain(_course_rules, _term("KKXQM", "开课学期")),
        relate=_course_links,
    )


def _teaching() -> DatasetSpec:
    teacher = "授课教师"
    course = "课程"
    place = "场所与课时"
    return _spec(
        code="ODS_SKXXSJ",
        name="授课信息",
        business_key_fields=("JGH", "KCH", "BJMC", "SKXQM", "CSMC"),
        department_field="KKDWMC",
        list_fields=("JGH", "JSXM", "KCH", "BJMC", "SKXQM"),
        groups=(
            (teacher, "教师工号和姓名须与已发布的教职工信息一致。"),
            (course, "专业、年级和课程代码须对应已发布课程。"),
            (place, "本场所课时和工作量须大于 0，线上课时不能超过本场所课时。"),
        ),
        fields=(
            _field("JGH", "授课教师工号", "text", teacher, required=True, max_length=20),
            _field("JSXM", "授课教师姓名", "text", teacher, required=True, max_length=36),
            _field("JSLB", "教师类别", "select", teacher, required=True, dict_code="D20"),
            _field("ZYMC", "专业名称", "text", course, required=True, max_length=60),
            _field("ZYDM", "专业代码", "text", course, required=True, max_length=6),
            _field("ZYCCM", "专业层次", "select", course, required=True, dict_code="D01"),
            _field("XZM", "学制", "select", course, required=True, dict_code="D02"),
            _field("PYFSM", "培养方式", "select", course, required=True, dict_code="D07"),
            _field("JTXS", "具体形式", "select", course, dict_code="D08"),
            _field("SYLXM", "生源类型", "select", course, required=True, dict_code="D09"),
            _field("NJ", "授课年级", "select", course, required=True, dict_code="D11"),
            _field("KCMC", "课程名称", "text", course, required=True, max_length=60),
            _field("KCH", "课程代码", "text", course, required=True, max_length=20),
            _field("SKXQM", "授课学期", "text", course, required=True, max_length=20),
            _department("KKDWMC", "开课单位名称", course),
            _field("SKRW", "授课任务", "select", place, required=True, dict_code="D68"),
            _field("CSWZ", "场所位置", "select", place, required=True, dict_code="D69"),
            _field("CSMC", "场所名称", "text", place, max_length=60),
            _field("CSMPH", "场所门牌号", "text", place, max_length=20),
            _field("SZLYMC", "所在楼宇名称", "text", place, max_length=60),
            _field("SZXQMC", "所在校区", "text", place, max_length=60),
            _field("BJMC", "班级名称", "text", place, required=True, max_length=60),
            _field("BCSKSS", "本场所教学课时数", "decimal", place, required=True),
            _field("XSKSS", "线上教学课时数", "decimal", place, required=True),
            _field("JXGZL", "教师教学工作量", "decimal", place, required=True),
        ),
        model=TeachingAssignment,
        hook=_chain(_teaching_rules, _term("SKXQM", "授课学期")),
        relate=_teaching_links,
    )


def _student() -> DatasetSpec:
    identity = "身份"
    status_group = "学籍"
    enroll = "招生"
    return _spec(
        code="ODS_XSJBSJ",
        name="在校生基本信息",
        business_key_fields=("XH",),
        department_field="YXBMCMC",
        list_fields=("XH", "XSXM", "ZYDM", "BJMC", "YXBMCMC"),
        groups=(
            (identity, "身份证号在列表中脱敏。"),
            (status_group, "专业代码和名称须与已发布专业一致。"),
            (enroll, None),
        ),
        fields=(
            _field("XH", "学号", "text", identity, required=True, max_length=20),
            _field("XSXM", "姓名", "text", identity, required=True, max_length=36),
            _field("XB", "性别", "select", identity, required=True, dict_code="D55"),
            _field("CSRQ", "出生日期", "date", identity, required=True),
            _field(
                "SFZJH",
                "身份证号",
                "text",
                identity,
                required=True,
                max_length=20,
                sensitive=True,
            ),
            _field("ZZMM", "政治面貌", "select", identity, required=True, dict_code="D21"),
            _field("MZ", "民族", "select", identity, required=True, dict_code="D22"),
            _field(
                "SYDGJDQ", "生源地国家（地区）", "select", identity, required=True, dict_code="D63"
            ),
            _field("SYDSF", "生源地省份", "select", identity, dict_code="D64"),
            _field("SYDDS", "生源地地市", "select", identity, dict_code="D65"),
            _field("LYJD", "来自军队", "select", identity, required=True, dict_code="D56"),
            _flag("SFCZHKZNC", "是否常住户口在农村", identity),
            _department("YXBMCMC", "所属院系部", status_group),
            _field("ZYMC", "专业名称", "text", status_group, required=True, max_length=60),
            _field("ZYDM", "专业代码", "text", status_group, required=True, max_length=6),
            _field("ZYCCM", "专业层次", "select", status_group, required=True, dict_code="D01"),
            _field("XZM", "学制", "select", status_group, required=True, dict_code="D02"),
            _field("PYFSM", "培养方式", "select", status_group, required=True, dict_code="D07"),
            _field("JTXS", "具体形式", "select", status_group, dict_code="D08"),
            _field("NJ", "年级", "select", status_group, required=True, dict_code="D11"),
            _field("BJMC", "班级名称", "text", status_group, required=True, max_length=60),
            _field("XJZT", "学籍状态", "select", status_group, required=True, dict_code="D57"),
            _field("RXRQ", "入学日期", "month", status_group, required=True),
            _field("ZSFS", "招生方式", "select", enroll, required=True, dict_code="D59"),
            _field("SYLXM", "生源类型", "select", enroll, required=True, dict_code="D09"),
            _field("BYXXMC", "毕业学校名称", "text", enroll, required=True, max_length=100),
            _field("FSRYQK", "四辅人员情况", "select", enroll, dict_code="D61"),
            _field("RXZF", "入学总分", "decimal", enroll, required=True),
            _field("SFCJ", "是否残疾", "select", enroll, required=True, dict_code="D62"),
            _flag("SFJDLPKPH", "是否建档立卡贫困户", enroll),
            _flag("SFTXXZ", "是否弹性学制", enroll),
        ),
        model=Student,
        hook=lambda _data, _errors: None,
        relate=_student_links,
    )
