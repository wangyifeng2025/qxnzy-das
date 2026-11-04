"""内置权限、角色与部门定义。

权限编码采用 `模块:动作`。角色按《数据标准规范》第 9 章填报职责划分：
教师（本人）、系部数据管理员（本部门）、业务部门审核员（跨系部审核）、信息中心管理员（全校）。
"""

from app.models.system import DataScope, DepartmentKind

# (编码, 名称, 模块, 排序)
PERMISSIONS: list[tuple[str, str, str, int]] = [
    ("home:view", "查看采集总览", "工作台", 10),
    ("fill:submit", "填报业务数据", "数据采集", 20),
    ("fill:view", "查看填报进度", "数据采集", 21),
    ("ai-parse:use", "使用文件解析入库", "数据采集", 22),
    ("review:manage", "审核与批量导入", "数据采集", 23),
    ("schema:manage", "管理数据表与字段", "数据治理", 30),
    ("api-task:manage", "管理 API 采集任务", "数据治理", 31),
    ("open-api:manage", "管理对外数据接口", "数据治理", 32),
    ("quality:view", "查看采集日志与质量", "数据治理", 33),
    ("user:read", "查看用户", "系统管理", 40),
    ("user:write", "维护用户", "系统管理", 41),
    ("role:read", "查看角色与权限", "系统管理", 42),
    ("role:write", "维护角色与权限", "系统管理", 43),
    ("department:read", "查看系部", "系统管理", 44),
    ("department:write", "维护系部", "系统管理", 45),
    ("dict:read", "查看数据字典", "系统管理", 46),
    ("dict:write", "维护数据字典", "系统管理", 47),
    ("audit:read", "查看审计日志", "系统管理", 48),
]

ALL_PERMISSION_CODES = [code for code, _, _, _ in PERMISSIONS]

# (编码, 名称, 说明, 数据范围, 权限编码列表, 排序)
ROLES: list[tuple[str, str, str, str, list[str], int]] = [
    (
        "teacher",
        "教师",
        "填报并维护本人的教师类数据",
        DataScope.SELF,
        ["fill:submit", "fill:view", "ai-parse:use", "department:read", "dict:read"],
        1,
    ),
    (
        "staff",
        "系部数据管理员",
        "按模板采集、初审并提交本系部数据",
        DataScope.DEPARTMENT,
        [
            "fill:submit",
            "fill:view",
            "ai-parse:use",
            "review:manage",
            "user:read",
            "department:read",
            "dict:read",
        ],
        2,
    ),
    (
        "auditor",
        "业务部门审核员",
        "组织人事部、科研处、教务处按数据域审核并填写全校数据",
        DataScope.ALL,
        [
            "home:view",
            "fill:submit",
            "fill:view",
            "ai-parse:use",
            "review:manage",
            "quality:view",
            "department:read",
            "dict:read",
        ],
        3,
    ),
    (
        "admin",
        "信息中心管理员",
        "标准归口管理、平台建设与运维、数据质量监测",
        DataScope.ALL,
        ALL_PERMISSION_CODES,
        4,
    ),
]

# (编码, 名称, 类型, 排序, 负责人, 单位职能, 上级编码)
# 来源：部门管理导出。开课单位记为教学部门，职能为「其他」记为其他，其余为职能部门。
DEPARTMENTS: list[tuple[str, str, str, int, str | None, str | None, str | None]] = [
    ("BM01", "医护系", DepartmentKind.TEACHING, 1, "罗厚成", "教学院系部", None),
    ("BM02", "商务系", DepartmentKind.TEACHING, 2, "祁根深", "教学院系部",None),
    ("BM03", "生物工程系", DepartmentKind.TEACHING, 3, "冉光鑫", "教学院系部",None),
    ("BM04", "机械与电子工程系", DepartmentKind.TEACHING, 4, "王一锋", "教学院系部",None),
    ("BM05", "水利电力工程系", DepartmentKind.TEACHING, 5, "邓毅", "教学院系部",None),
    ("BM06", "中等职业学校", DepartmentKind.FUNCTIONAL, 6, "张宏熹", "教学和学生管理",None),
    ("BM07", "教务处", DepartmentKind.FUNCTIONAL, 7, "米树文", "教学和学生管理",None),
    ("BM08", "马列主义教学部", DepartmentKind.TEACHING, 8, "唐莉", "教学管理",None),
    ("BM09", "公共基础教学部", DepartmentKind.TEACHING, 9, "况照祥", "教学管理",None),
    ("BM10", "党政办", DepartmentKind.FUNCTIONAL, 10, "龚略", "综合管理",None),
    ("BM11", "组织人事部", DepartmentKind.FUNCTIONAL, 11, "黄甫攀", "人事管理",None),
    ("BM12", "宣传部", DepartmentKind.FUNCTIONAL, 12, "徐伊伊", "信息化管理",None),
    ("BM13", "统战部", DepartmentKind.FUNCTIONAL, 13, "雷乃良", "群团组织",None),
    ("BM14", "工会", DepartmentKind.FUNCTIONAL, 14, "聂红", "群团组织",None),
    ("BM15", "团委", DepartmentKind.FUNCTIONAL, 15, "黄江志", "群团组织",None),
    ("BM16", "总务处", DepartmentKind.FUNCTIONAL, 16, "王玲", "后勤保障",None),
    ("BM17", "保卫处", DepartmentKind.OTHER, 17, "郭锐", "其他",None),
    ("BM18", "财务处", DepartmentKind.OTHER, 18, "王顺友", "其他",None),
    ("BM19", "学生资助管理中心", DepartmentKind.FUNCTIONAL, 19, "聂红", "学生管理",None),
    ("BM20", "招生就业处", DepartmentKind.FUNCTIONAL, 20, "袁权", "招生就业",None),
    ("BM21", "学生工作部", DepartmentKind.FUNCTIONAL, 21, "杨波", "学生管理",None),
    ("BM22", "科研处", DepartmentKind.FUNCTIONAL, 22, "李宝贵", "科研机构",None),
    ("BM23", "继续教育与培训部", DepartmentKind.OTHER, 23, "甘开国", "其他",None),
    ("BM24", "纪委", DepartmentKind.OTHER, 24, "何冰", "其他",None),
    ("BM25", "图书馆", DepartmentKind.FUNCTIONAL, 25, "黄振栋", "图书与数字资源管理",None),
    ("BM26", "院领导", DepartmentKind.OTHER, 26, "李光武", "其他",None),
    ("BM27", "信息中心", DepartmentKind.FUNCTIONAL, 27, "王一锋", "信息化管理",None),
]

ADMIN_DEPARTMENT_CODE = "BM27"

# (账号, 姓名, 角色编码, 部门编码, 岗位, 是否超级管理员)
TEST_USERS: list[tuple[str, str, str, str | None, str | None, bool]] = [
    ("admin", "系统管理员", "admin", ADMIN_DEPARTMENT_CODE, "超级管理员", True),
    ("2004020159", "王一锋", "admin", ADMIN_DEPARTMENT_CODE, "信息中心负责人", True),
    ("2015200012", "罗胜", "staff", "BM04", None, False),
    ("2024020008", "谭元霸", "teacher", "BM04", None, False),
    ("zzrsb01", "组织人事部审核员", "auditor", "BM11", "业务部门审核员", False),
    ("kyc01", "科研处审核员", "auditor", "BM22", "业务部门审核员", False),
    ("jwc01", "教务处审核员", "auditor", "BM07", "业务部门审核员", False),
]

# (账号, 姓名, 角色编码, 部门编码, 岗位)
# 初始密码使用 INITIAL_ADMIN_PASSWORD，已存在时不覆盖密码
SUPER_ADMIN: tuple[str, str, str, str | None, str | None] = (
    "admin",
    "系统管理员",
    "admin",
    ADMIN_DEPARTMENT_CODE,
    "超级管理员",
)

TEST_USER_PASSWORD = "123456"
