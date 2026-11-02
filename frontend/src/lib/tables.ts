export type FieldType = "text" | "select" | "date" | "number" | "textarea";

export type FormField = {
  label: string;
  key: string;
  type: FieldType;
  required?: boolean;
  options?: string[];
  placeholder?: string;
  value?: string;
  span?: "full";
  hint?: string;
};

export type FormSection = {
  title: string;
  desc?: string;
  fields: FormField[];
};

export type DataTableDef = {
  id: string;
  name: string;
  dept: string;
  code: string;
  kind: "single" | "multi";
  collected: string;
  expected: string;
  rate: string;
  status: "已达标" | "进行中" | "需关注";
  sections: FormSection[];
};

const depts = ["医护系", "商务系", "生物工程系", "机械与电子工程系", "水利电力工程系", "马列主义教学部", "公共基础教学部"];

export const DATA_TABLES: DataTableDef[] = [
  {
    id: "major",
    name: "专业设置数据",
    dept: "教务处",
    code: "T_MAJOR",
    kind: "single",
    collected: "0",
    expected: "0",
    rate: "—",
    status: "进行中",
    sections: [
      {
        title: "专业信息",
        desc: "学校开设专业的基础信息与招生状态",
        fields: [
          { label: "专业代码", key: "majorCode", type: "text", required: true, hint: "教育部专业目录代码" },
          { label: "专业名称", key: "majorName", type: "text", required: true },
          { label: "所属系部", key: "department", type: "select", required: true, options: depts },
          { label: "专业负责人", key: "leader", type: "text", required: true },
          { label: "学制", key: "duration", type: "select", required: true, options: ["三年制", "二年制", "五年制"] },
          { label: "招生状态", key: "enrollment", type: "select", required: true, options: ["招生中", "暂停招生", "停招"] },
          { label: "开设年份", key: "openYear", type: "number" },
          { label: "在校生数", key: "studentCount", type: "number", required: true },
          { label: "核心课程", key: "coreCourses", type: "textarea", required: true, span: "full" },
        ],
      },
    ],
  },
  {
    id: "staff",
    name: "教职工基本信息数据",
    dept: "人事处",
    code: "T_STAFF_BASE",
    kind: "single",
    collected: "0",
    expected: "0",
    rate: "—",
    status: "进行中",
    sections: [
      {
        title: "身份信息",
        desc: "每人仅保留一条，更新后覆盖原记录",
        fields: [
          { label: "工号", key: "staffNo", type: "text", required: true, hint: "主键，提交后不可修改" },
          { label: "姓名", key: "name", type: "text", required: true },
          { label: "性别", key: "gender", type: "select", required: true, options: ["男", "女"] },
          { label: "出生日期", key: "birthday", type: "date", required: true },
          { label: "民族", key: "ethnicity", type: "select", options: ["汉族", "布依族", "苗族", "侗族", "彝族", "其他"] },
          { label: "身份证号", key: "idCard", type: "text", required: true },
        ],
      },
      {
        title: "岗位信息",
        fields: [
          { label: "所属系部", key: "department", type: "select", required: true, options: depts },
          { label: "岗位类别", key: "postType", type: "select", required: true, options: ["专任教师", "辅导员", "行政管理人员", "教辅人员"] },
          { label: "职称", key: "title", type: "select", required: true, options: ["教授", "副教授", "讲师", "助教", "未定级"] },
          { label: "学历", key: "education", type: "select", required: true, options: ["博士研究生", "硕士研究生", "本科", "专科"] },
          { label: "入职日期", key: "hireDate", type: "date", required: true },
          { label: "是否双师型教师", key: "dualTeacher", type: "select", options: ["是", "否"] },
        ],
      },
    ],
  },
  {
    id: "training",
    name: "教师培训与交流数据",
    dept: "教师工作部",
    code: "T_TEACHER_TRAINING",
    kind: "multi",
    collected: "0",
    expected: "0",
    rate: "—",
    status: "进行中",
    sections: [
      {
        title: "培训记录",
        desc: "按条登记，同一教师可有多条",
        fields: [
          { label: "培训名称", key: "trainingName", type: "text", required: true, placeholder: "请输入培训项目名称" },
          { label: "培训类别", key: "trainingType", type: "select", required: true, options: ["国家级培训", "省级培训", "州级培训", "校本培训"] },
          { label: "举办单位", key: "organizer", type: "text", required: true },
          { label: "开始日期", key: "startDate", type: "date", required: true },
          { label: "结束日期", key: "endDate", type: "date", required: true },
          { label: "学时", key: "hours", type: "number", required: true },
          { label: "培训地点", key: "location", type: "text", required: true },
          { label: "结业证书编号", key: "certificateNo", type: "text" },
        ],
      },
    ],
  },
  {
    id: "award",
    name: "教师获奖信息数据",
    dept: "教师工作部",
    code: "T_TEACHER_AWARD",
    kind: "multi",
    collected: "0",
    expected: "0",
    rate: "—",
    status: "进行中",
    sections: [
      {
        title: "获奖记录",
        fields: [
          { label: "获奖名称", key: "awardName", type: "text", required: true },
          { label: "级别", key: "awardLevel", type: "select", required: true, options: ["国家级", "省级", "州级", "校级"] },
          { label: "奖项类别", key: "awardType", type: "select", required: true, options: ["教学成果", "技能竞赛", "指导学生获奖", "荣誉称号"] },
          { label: "颁奖单位", key: "issuer", type: "text", required: true },
          { label: "获奖日期", key: "awardDate", type: "date", required: true },
          { label: "排名", key: "ranking", type: "number", required: true },
          { label: "证书编号", key: "certificateNo", type: "text" },
        ],
      },
    ],
  },
  {
    id: "paper",
    name: "教师论文著作数据",
    dept: "科研处",
    code: "T_TEACHER_PAPER",
    kind: "multi",
    collected: "0",
    expected: "0",
    rate: "—",
    status: "进行中",
    sections: [
      {
        title: "成果信息",
        fields: [
          { label: "成果名称", key: "achievementName", type: "text", required: true, span: "full" },
          { label: "成果类型", key: "achievementType", type: "select", required: true, options: ["期刊论文", "教材", "专著"] },
          { label: "刊物 / 出版社", key: "publisher", type: "text", required: true },
          { label: "发表时间", key: "publishDate", type: "date", required: true },
          { label: "ISSN / ISBN", key: "isbn", type: "text", hint: "期刊论文请填写 ISSN" },
          { label: "作者排序", key: "authorRank", type: "number", required: true },
        ],
      },
    ],
  },
  {
    id: "vertical",
    name: "教师科研项目基本数据（纵向）",
    dept: "科研处",
    code: "T_RESEARCH_VERTICAL",
    kind: "multi",
    collected: "0",
    expected: "0",
    rate: "—",
    status: "进行中",
    sections: [
      {
        title: "项目信息",
        fields: [
          { label: "项目名称", key: "projectName", type: "text", required: true, span: "full" },
          { label: "项目级别", key: "projectLevel", type: "select", required: true, options: ["国家级", "省部级", "州厅级", "校级"] },
          { label: "项目编号", key: "projectNo", type: "text", required: true },
          { label: "负责人", key: "leader", type: "text", required: true },
          { label: "立项日期", key: "startDate", type: "date", required: true },
          { label: "批准经费（万元）", key: "funding", type: "number", required: true },
          { label: "项目状态", key: "projectStatus", type: "select", required: true, options: ["在研", "结题", "延期"] },
        ],
      },
    ],
  },
  {
    id: "horizontal",
    name: "教师横向课题数据",
    dept: "科研处",
    code: "T_RESEARCH_HORIZONTAL",
    kind: "multi",
    collected: "0",
    expected: "0",
    rate: "—",
    status: "进行中",
    sections: [
      {
        title: "合同信息",
        fields: [
          { label: "课题名称", key: "projectName", type: "text", required: true, span: "full" },
          { label: "合同编号", key: "contractNo", type: "text", required: true },
          { label: "委托单位", key: "client", type: "text", required: true },
          { label: "合同金额（万元）", key: "contractAmount", type: "number", required: true },
          { label: "到账金额（万元）", key: "receivedAmount", type: "number", required: true },
          { label: "签订日期", key: "signDate", type: "date", required: true },
          { label: "项目状态", key: "projectStatus", type: "select", required: true, options: ["执行中", "已结题"] },
        ],
      },
    ],
  },
  {
    id: "practice",
    name: "教师企业实践锻炼数据表",
    dept: "校企合作处",
    code: "T_TEACHER_PRACTICE",
    kind: "multi",
    collected: "0",
    expected: "0",
    rate: "—",
    status: "进行中",
    sections: [
      {
        title: "实践记录",
        fields: [
          { label: "实践单位", key: "enterprise", type: "text", required: true },
          { label: "实践岗位", key: "position", type: "text", required: true },
          { label: "实践类型", key: "practiceType", type: "select", required: true, options: ["脱产实践", "跟岗实践"] },
          { label: "开始日期", key: "startDate", type: "date", required: true },
          { label: "结束日期", key: "endDate", type: "date", required: true },
          { label: "天数", key: "days", type: "number", required: true },
          { label: "实践内容", key: "content", type: "textarea", span: "full" },
        ],
      },
    ],
  },
  {
    id: "ip",
    name: "教师知识产权数据",
    dept: "科研处",
    code: "T_TEACHER_IP",
    kind: "multi",
    collected: "0",
    expected: "0",
    rate: "—",
    status: "进行中",
    sections: [
      {
        title: "知识产权",
        fields: [
          { label: "成果名称", key: "ipName", type: "text", required: true, span: "full" },
          { label: "类型", key: "ipType", type: "select", required: true, options: ["发明专利", "实用新型专利", "软件著作权"] },
          { label: "授权号", key: "authNo", type: "text", required: true },
          { label: "申请日期", key: "applyDate", type: "date", required: true },
          { label: "授权日期", key: "grantDate", type: "date", required: true },
          { label: "法律状态", key: "legalStatus", type: "select", required: true, options: ["有效", "失效"] },
        ],
      },
    ],
  },
  {
    id: "course",
    name: "课程基本数据",
    dept: "教务处",
    code: "T_COURSE",
    kind: "single",
    collected: "0",
    expected: "0",
    rate: "—",
    status: "进行中",
    sections: [
      {
        title: "课程信息",
        fields: [
          { label: "课程代码", key: "courseCode", type: "text", required: true },
          { label: "课程名称", key: "courseName", type: "text", required: true },
          { label: "所属专业", key: "major", type: "text", required: true },
          { label: "开课系部", key: "department", type: "select", required: true, options: depts },
          { label: "学分", key: "credits", type: "number", required: true },
          { label: "总学时", key: "totalHours", type: "number", required: true },
          { label: "考核方式", key: "assessment", type: "select", options: ["考试", "考查", "过程性考核"] },
        ],
      },
    ],
  },
  {
    id: "teaching",
    name: "授课信息数据",
    dept: "教务处",
    code: "T_TEACHING",
    kind: "multi",
    collected: "0",
    expected: "0",
    rate: "—",
    status: "进行中",
    sections: [
      {
        title: "授课安排",
        fields: [
          { label: "课程代码", key: "courseCode", type: "text", required: true },
          { label: "课程名称", key: "courseName", type: "text", required: true },
          { label: "授课班级", key: "className", type: "text", required: true },
          { label: "学期", key: "semester", type: "select", required: true, options: ["2025-2026-1", "2025-2026-2", "2024-2025-2"] },
          { label: "周学时", key: "weeklyHours", type: "number", required: true },
          { label: "总学时", key: "totalHours", type: "number", required: true },
          { label: "授课地点", key: "location", type: "text", required: true },
          { label: "授课方式", key: "mode", type: "select", options: ["线下授课", "线上授课", "线上线下混合"] },
        ],
      },
    ],
  },
  {
    id: "student",
    name: "全日制高职在校生基本信息表",
    dept: "学生工作处",
    code: "T_STUDENT_BASE",
    kind: "single",
    collected: "0",
    expected: "0",
    rate: "—",
    status: "进行中",
    sections: [
      {
        title: "学生基本信息",
        fields: [
          { label: "学号", key: "studentNo", type: "text", required: true },
          { label: "姓名", key: "name", type: "text", required: true },
          { label: "性别", key: "gender", type: "select", required: true, options: ["男", "女"] },
          { label: "身份证号", key: "idCard", type: "text", required: true },
          { label: "所属系部", key: "department", type: "select", required: true, options: depts },
          { label: "专业", key: "major", type: "text", required: true },
          { label: "班级", key: "className", type: "text", required: true },
          { label: "学籍状态", key: "status", type: "select", required: true, options: ["在籍", "休学", "保留学籍", "退学"] },
        ],
      },
    ],
  },
];

export const SCHEMA_FIELDS: Record<string, { cn: string; code: string; type: string; required: boolean; source: string; fill: string }[]> = {
  staff: [
    { cn: "工号", code: "staff_no", type: "VARCHAR(20)", required: true, source: "业务系统 API", fill: "—" },
    { cn: "姓名", code: "name", type: "VARCHAR(50)", required: true, source: "业务系统 API", fill: "—" },
    { cn: "性别", code: "gender", type: "VARCHAR(4)", required: true, source: "业务系统 API", fill: "—" },
    { cn: "身份证号", code: "id_card", type: "VARCHAR(18)", required: true, source: "业务系统 API", fill: "—" },
    { cn: "所属系部", code: "dept_id", type: "VARCHAR(32)", required: true, source: "业务系统 API", fill: "—" },
    { cn: "岗位类别", code: "post_type", type: "VARCHAR(20)", required: true, source: "手动 / API", fill: "—" },
    { cn: "职称", code: "title", type: "VARCHAR(20)", required: true, source: "手动填报", fill: "—" },
    { cn: "学历", code: "education", type: "VARCHAR(20)", required: true, source: "手动填报", fill: "—" },
    { cn: "入职日期", code: "hire_date", type: "DATE", required: true, source: "业务系统 API", fill: "—" },
    { cn: "手机号码", code: "phone", type: "VARCHAR(20)", required: true, source: "手动填报", fill: "—" },
    { cn: "电子邮箱", code: "email", type: "VARCHAR(100)", required: false, source: "手动填报", fill: "—" },
    { cn: "是否双师型教师", code: "dual_teacher", type: "BOOLEAN", required: false, source: "手动填报", fill: "—" },
  ],
};
