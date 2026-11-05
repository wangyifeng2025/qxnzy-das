from app.models.academic import Course, Major, TeachingAssignment
from app.models.base import Base
from app.models.ingestion import IngestCandidate, IngestFile, IngestTask
from app.models.records import BizRecord, BizRecordEvent, BizRecordVersion
from app.models.research import HorizontalResearchProject, IntellectualProperty, ResearchProject
from app.models.staff import StaffMember
from app.models.students import SeptemberNewStudent, Student
from app.models.system import (
    AuditLog,
    DataScope,
    Department,
    DepartmentKind,
    DictItem,
    DictType,
    Permission,
    Role,
    User,
    UserStatus,
)
from app.models.teacher_activity import (
    EnterprisePractice,
    TeacherAward,
    TeacherPublication,
    TeacherTraining,
)

__all__ = [
    "AuditLog",
    "Base",
    "BizRecord",
    "BizRecordEvent",
    "BizRecordVersion",
    "Course",
    "DataScope",
    "Department",
    "DepartmentKind",
    "DictItem",
    "DictType",
    "EnterprisePractice",
    "HorizontalResearchProject",
    "IngestCandidate",
    "IngestFile",
    "IngestTask",
    "IntellectualProperty",
    "Major",
    "Permission",
    "ResearchProject",
    "Role",
    "SeptemberNewStudent",
    "StaffMember",
    "Student",
    "TeacherAward",
    "TeacherPublication",
    "TeacherTraining",
    "TeachingAssignment",
    "User",
    "UserStatus",
]
