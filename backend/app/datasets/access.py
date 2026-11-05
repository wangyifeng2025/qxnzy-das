"""数据集的填写方、可见范围和审核环节。

环节序列由数据域和填写方决定，不写死三级。获奖信息的业务审核部门是所属系部，
因此没有职能部门环节。
"""

from app.datasets.spec import DatasetSpec
from app.models.records import BizRecord
from app.models.system import User

OWNER_DEPARTMENT = "owner_department"


def role_codes(user: User) -> set[str]:
    return {role.code for role in user.roles}


def is_center(user: User) -> bool:
    return user.is_superuser or "admin" in role_codes(user)


def review_steps(spec: DatasetSpec, filler_type: str) -> list[str]:
    """提交后需要经过的状态。空列表表示提交即发布。"""
    if filler_type == "center":
        return []
    steps: list[str] = []
    if spec.category == "teacher" and filler_type == "teacher":
        steps.append("pending_dept")
    if spec.review_department != OWNER_DEPARTMENT and filler_type in {"teacher", "department"}:
        steps.append("pending_domain")
    steps.append("pending_center")
    return steps


def filler_type_for(user: User, spec: DatasetSpec) -> str | None:
    if is_center(user):
        return "center"
    if user.department is None:
        return None
    codes = role_codes(user)
    if (
        "auditor" in codes
        and spec.review_department != OWNER_DEPARTMENT
        and user.department.code == spec.review_department
    ):
        return "domain"
    if spec.category != "teacher":
        return None
    if "staff" in codes:
        return "department"
    if "teacher" in codes:
        return "teacher"
    return None


def can_fill(user: User, spec: DatasetSpec) -> bool:
    if filler_type_for(user, spec) is None:
        return False
    return user.is_superuser or "fill:submit" in user.permission_codes


def can_review_dataset(user: User, spec: DatasetSpec) -> bool:
    if not (user.is_superuser or "review:manage" in user.permission_codes):
        return False
    if is_center(user):
        return True
    if user.department is None:
        return False
    codes = role_codes(user)
    if spec.category == "teacher" and "staff" in codes:
        return True
    return (
        "auditor" in codes
        and spec.review_department != OWNER_DEPARTMENT
        and user.department.code == spec.review_department
    )


def can_view(user: User, spec: DatasetSpec, record: BizRecord) -> bool:
    if is_center(user):
        return True
    if spec.category != "teacher":
        return _domain_auditor(user, spec)
    if user.department is None:
        return record.owner_account == user.account
    codes = role_codes(user)
    if (
        "auditor" in codes
        and spec.review_department != OWNER_DEPARTMENT
        and user.department.code == spec.review_department
    ):
        return True
    if "staff" in codes and record.department_id == user.department_id:
        return True
    return record.owner_account == user.account


def _domain_auditor(user: User, spec: DatasetSpec) -> bool:
    return (
        user.department is not None
        and "auditor" in role_codes(user)
        and spec.review_department != OWNER_DEPARTMENT
        and user.department.code == spec.review_department
    )


def can_revise(user: User, spec: DatasetSpec, record: BizRecord) -> bool:
    """能否把已发布记录改回草稿重新走流程。

    发布动作只由信息中心完成（各数据域的最后一个环节都是信息中心审核），
    因此已发布数据也由信息中心统一维护：填报人、系部数据管理员和业务部门审核员
    都不能把自己提交并被发布的数据撤回为草稿。
    """
    return record.status == "published" and is_center(user) and can_fill(user, spec)


def can_act(user: User, spec: DatasetSpec, record: BizRecord, *, skip: bool = False) -> bool:
    """当前用户能否对这条待审记录执行通过、退回或跳级发布。"""
    if record.status not in {"pending_dept", "pending_domain", "pending_center"}:
        return False
    if not (user.is_superuser or "review:manage" in user.permission_codes or is_center(user)):
        return False
    own = record.filler_account == user.account
    if skip:
        return is_center(user)
    if own:
        return False
    if record.status == "pending_center":
        return is_center(user)
    if user.department is None:
        return False
    if record.status == "pending_dept":
        return "staff" in role_codes(user) and record.department_id == user.department_id
    return (
        "auditor" in role_codes(user)
        and spec.review_department != OWNER_DEPARTMENT
        and user.department.code == spec.review_department
    )
