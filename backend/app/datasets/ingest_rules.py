"""填报场景的别名与查库补全规则。

数据集定义只关心业务字段和校验；这里集中维护“同一字段在这所学校的各种叫法”
以及“哪些字段可以用已发布数据补全”，避免把导入细节散落到每个数据集里。
"""

from dataclasses import replace

from app.datasets.spec import DatasetSpec, Derive, FieldSpec, Lookup

_ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "ODS_ZYSZSJ": {
        "ZYMC": ("专业", "开设专业", "专业全称"),
        "ZYDM": ("专业编码", "专业代码（6位）", "教育部专业代码"),
        "ZYCCM": ("层次", "办学层次", "专业办学层次"),
        "XZM": ("学制年限", "修业年限", "基本学制"),
        "ZYDLMC": ("专业大类名称", "大类", "专业大类（国标）"),
        "ZYFLMC": ("专业类名称", "二级类", "专业类别"),
        "PZSZNY": ("批准设置时间", "批准时间", "设置时间"),
        "SCZSNY": ("首次招生时间", "开始招生时间", "首届招生时间"),
        "ZYSSYXBMC": ("院系", "所属院系", "系部", "专业所在系部"),
        "SYXWLBM": ("学位门类", "授予学位门类"),
        "SFZDZY": ("重点专业", "是否重点"),
        "ZDZYJBM": ("重点级别", "专业级别"),
        "ZDZYLXM": ("重点类型", "类型"),
        "ZYPPCYQK": ("产业匹配情况", "匹配产业情况"),
        "CYMC": ("对应产业", "服务产业"),
        "GNDW": ("功能定位说明", "定位"),
        "ZYJYDLMC": ("职业大类", "职业类别大类", "大类名称"),
        "ZYJYFLMC": ("职业中类", "职业类别中类", "中类名称"),
        "ZYJYXLMC": ("职业小类", "职业类别小类", "小类名称"),
    },
    "ODS_KCJBSJ": {
        "ZYMC": ("所属专业", "专业", "开设专业"),
        "ZYDM": ("专业编码", "所属专业代码"),
        "ZYCCM": ("层次", "办学层次"),
        "XZM": ("学制年限", "修业年限"),
        "PYFSM": ("培养形式", "培养模式"),
        "SYLXM": ("生源类别", "招生对象"),
        "NJ": ("年级", "适用年级"),
        "KCMC": ("课程", "课程名", "课程中文名称"),
        "KCH": ("课程编码", "课程号"),
        "KCLXM": ("课程类别", "课程类型"),
        "KCSXM": ("课程属性", "课程类别属性"),
        "KCXZM": ("课程性质", "修读性质"),
        "KKXQM": ("开课学期", "学期"),
        "KKDWMC": ("开课部门", "开课单位", "院系", "系部"),
        "SFXQHZKFKC": ("校企合作开发", "校企合作开发课程"),
        "HZQYMC": ("合作企业", "企业名称"),
        "ZXJPC": ("精品课程", "在线精品课"),
        "KZZXS": ("总学时", "学时", "课程学时"),
        "SJJXKSS": ("实践学时", "实践教学总学时"),
    },
    "ODS_SKXXSJ": {
        "JGH": ("工号", "教师工号", "教工号"),
        "JSXM": ("姓名", "教师姓名", "授课教师"),
        "JSLB": ("人员类别", "教师类型"),
        "ZYMC": ("所属专业", "专业"),
        "ZYDM": ("专业编码", "所属专业代码"),
        "ZYCCM": ("层次", "办学层次"),
        "XZM": ("学制年限", "修业年限"),
        "PYFSM": ("培养形式",),
        "SYLXM": ("生源类别",),
        "NJ": ("年级", "授课年级"),
        "KCMC": ("课程", "课程名"),
        "KCH": ("课程编码", "课程号"),
        "SKXQM": ("学期", "授课学期", "开课学期"),
        "KKDWMC": ("开课部门", "开课单位", "院系"),
        "CSWZ": ("场所类型", "场地类型"),
        "CSMC": ("场所", "上课地点", "教学场所"),
        "CSMPH": ("门牌号", "教室号"),
        "SZLYMC": ("楼宇", "所在楼栋"),
        "SZXQMC": ("校区", "所在校区"),
        "BJMC": ("班级", "授课班级"),
        "BCSKSS": ("课时", "本场所课时", "面授课时"),
        "XSKSS": ("线上课时", "线上教学课时"),
        "JXGZL": ("工作量", "教学工作量"),
    },
    "ODS_XSJBSJ": {
        "XH": ("学号", "学生学号"),
        "XSXM": ("姓名", "学生姓名"),
        "XB": ("性别",),
        "CSRQ": ("出生年月", "出生日期", "生日"),
        "SFZJH": ("身份证", "身份证号码", "身份证件号"),
        "ZZMM": ("政治面貌",),
        "MZ": ("民族",),
        "YXBMCMC": ("院系", "所属院系", "系部", "院系部"),
        "ZYMC": ("专业", "专业名称"),
        "ZYDM": ("专业编码", "专业代码"),
        "ZYCCM": ("层次", "办学层次"),
        "XZM": ("学制年限", "修业年限"),
        "PYFSM": ("培养形式",),
        "NJ": ("年级",),
        "BJMC": ("班级", "行政班"),
        "XJZT": ("学籍状态", "在校状态"),
        "RXRQ": ("入学年月", "入学时间"),
        "ZSFS": ("招生方式", "招生形式"),
        "SYLXM": ("生源类别", "生源类型"),
        "BYXXMC": ("毕业学校", "毕业中学"),
        "RXZF": ("入学总分", "总分", "入学成绩"),
        "SFCJ": ("是否残疾", "残疾"),
    },
    "ODS_XXJXSJ": {
        "JGH": ("工号", "教工号", "教师工号"),
        "JSXM": ("姓名", "教师姓名"),
        "YXBMCMC": ("院系", "所属院系", "系部", "部门"),
        "JSLB": ("人员类别", "教师类型"),
        "JXPXMC": ("培训项目", "培训名称", "项目名称"),
        "JXPXLX": ("培训类型", "培训交流类型"),
        "JXPXFS": ("培训方式", "培训形式"),
        "JBBMMC": ("举办单位", "主办单位", "举办部门"),
        "JXPXJB": ("培训级别", "级别"),
        "PXTS": ("天数", "培训天数", "时长"),
        "JXPXDD": ("培训地点", "地点"),
        "PCBMMC": ("派出单位", "派出部门"),
        "PCBMJB": ("派出级别", "派出部门级别"),
    },
    "ODS_JSHJSJ": {
        "DYHJRGH": ("获奖人工号", "第一获奖人工号", "工号"),
        "DYHJRXM": ("获奖人", "第一获奖人", "姓名"),
        "YXBMCMC": ("院系", "所属院系", "系部", "部门"),
        "JSLB": ("人员类别", "教师类型"),
        "HJMC": ("奖项名称", "获奖项目", "获奖名称"),
        "JB": ("获奖级别", "级别"),
        "DJ": ("获奖等级", "等级"),
        "HJLB": ("奖项类型", "奖项类别", "类别"),
        "BJDWMC": ("颁奖单位", "授予单位"),
        "HJRQ": ("获奖时间", "获奖年月", "获奖日期"),
        "HJRSC": ("获奖人排序", "排序", "获奖人顺序"),
    },
    "ODS_LWZZSJ": {
        "DYZGH": ("作者工号", "第一作者工号", "工号"),
        "DYZXM": ("作者", "第一作者", "姓名"),
        "YXBMCMC": ("院系", "所属院系", "系部", "部门"),
        "JSLB": ("人员类别", "教师类型"),
        "ZZMC": ("论文名称", "著作名称", "成果名称"),
        "CGSX": ("成果类型", "成果形式"),
        "LWFL": ("论文分类", "著作分类", "分类"),
        "CBSMC": ("出版社", "期刊名称", "发表刊物"),
        "FBRQ": ("发表日期", "出版日期", "发表时间"),
        "WCDWSC": ("完成单位排序", "单位顺序"),
    },
    "ODS_JSQYJZSJSJ": {
        "JGH": ("工号", "教工号", "教师工号"),
        "JSXM": ("姓名", "教师姓名"),
        "YXBMCMC": ("院系", "所属院系", "系部", "部门"),
        "JSLB": ("人员类别", "教师类型"),
        "QYDLLX": ("企业类型", "实践类型"),
        "JSDWMC": ("接收单位", "实践单位"),
        "GWMC": ("实践岗位", "岗位"),
        "SJTS": ("实践天数", "天数", "时长"),
        "JSDDSZD": ("单位所在地", "所在地"),
        "PCBMMC": ("派出部门", "推荐部门"),
        "PCBMJB": ("派出级别", "派出部门级别"),
    },
    "ODS_KYXMJBSJ": {
        "DYZCRGH": ("主持人工号", "第一主持人工号", "工号"),
        "DYZCRXM": ("主持人", "第一主持人", "姓名"),
        "YXBMCMC": ("院系", "所属院系", "系部", "部门"),
        "JSLB": ("人员类别", "教师类型"),
        "KTMC": ("项目名称", "课题名称", "课题"),
        "KTFL": ("项目分类", "课题分类"),
        "KTXZ": ("项目性质", "课题性质"),
        "YJZT": ("项目状态", "研究状态"),
        "KTLY": ("项目来源", "课题来源"),
        "PZBMMC": ("批准单位", "主管部门", "批准部门"),
        "KTJB": ("项目级别", "课题级别"),
        "LXRQ": ("立项时间", "立项日期", "起始日期"),
        "JFLY": ("资金来源", "经费来源"),
        "LXJF": ("项目经费", "立项经费", "经费"),
        "JXRQ": ("结项时间", "结项日期", "结束日期"),
        "LJDKJE": ("到账金额", "累计到账金额"),
        "CYJSS": ("参与人数", "参研人数"),
    },
    "ODS_HXKTSJ": {
        "DYZCRGH": ("主持人工号", "第一主持人工号", "工号"),
        "DYZCRXM": ("主持人", "第一主持人", "姓名"),
        "YXBMCMC": ("院系", "所属院系", "系部", "部门"),
        "JSLB": ("人员类别", "教师类型"),
        "KTMC": ("项目名称", "课题名称", "课题"),
        "YJZT": ("项目状态", "研究状态"),
        "KTLY": ("项目来源", "课题来源"),
        "WTFMC": ("委托单位", "委托方", "委托方名称"),
        "LXRQ": ("立项时间", "立项日期"),
        "BXNDKJE": ("本年到账金额", "本学年到账金额"),
        "LJDKJE": ("到账金额", "累计到账金额"),
        "JXRQ": ("结项时间", "结项日期"),
        "FWLX": ("服务类别", "服务类型"),
    },
    "ODS_ZSCQSJ": {
        "DYFMRGH": ("发明人工号", "第一发明人工号", "工号"),
        "DYFMRXM": ("发明人", "第一发明人", "姓名"),
        "YXBMCMC": ("院系", "所属院系", "系部", "部门"),
        "JSLB": ("人员类别", "教师类型"),
        "ZSCQMC": ("知识产权名称", "专利名称", "项目名称"),
        "ZSCQBH": ("专利号", "知识产权号", "证书编号"),
        "XMLX": ("知识产权类型", "专利类型", "项目类型"),
        "HDRQ": ("获得时间", "授权日期", "获得日期"),
        "ZRXKJE": ("转让金额", "许可金额"),
        "SRFMC": ("受让方", "受让单位", "受让方名称"),
        "ZRXKRQ": ("转让日期", "许可日期"),
    },
}

_LOOKUPS: dict[str, tuple[Lookup, ...]] = {
    "ODS_KCJBSJ": (
        Lookup(
            source="major",
            by=("ZYDM",),
            fill=(("ZYMC", "ZYMC"), ("ZYCCM", "ZYCCM"), ("XZM", "XZM")),
            name="专业",
        ),
        Lookup(
            source="major",
            by=("ZYMC",),
            fill=(("ZYDM", "ZYDM"), ("ZYCCM", "ZYCCM"), ("XZM", "XZM")),
            name="专业",
        ),
    ),
    "ODS_SKXXSJ": (
        Lookup(
            source="major",
            by=("ZYDM",),
            fill=(("ZYMC", "ZYMC"), ("ZYCCM", "ZYCCM"), ("XZM", "XZM")),
            name="专业",
        ),
        Lookup(source="staff", by=("JGH",), fill=(("JSXM", "JSXM"),), name="教职工"),
        Lookup(source="course", by=("ZYDM", "KCH"), fill=(("KCMC", "KCMC"),), name="课程"),
    ),
    "ODS_XSJBSJ": (
        Lookup(
            source="major",
            by=("ZYDM",),
            fill=(("ZYMC", "ZYMC"), ("ZYCCM", "ZYCCM"), ("XZM", "XZM")),
            name="专业",
        ),
    ),
}


def _with_aliases(spec: DatasetSpec) -> tuple[FieldSpec, ...]:
    aliases = _ALIASES.get(spec.code, {})
    if not aliases:
        return spec.fields
    return tuple(
        replace(field, aliases=field.aliases or aliases.get(field.code, ()))
        for field in spec.fields
    )


def _derives(spec: DatasetSpec) -> tuple[Derive, ...]:
    rules = [Derive(kind="department", fill=(spec.department_field,))]
    if spec.owner_field and spec.owner_name_field:
        rules.append(Derive(kind="owner", fill=(spec.owner_field, spec.owner_name_field)))
    return tuple(rules)


def with_ingestion_rules(spec: DatasetSpec) -> DatasetSpec:
    """给数据集补齐别名、查库补全和推导规则。"""
    return replace(
        spec,
        fields=_with_aliases(spec),
        lookups=spec.lookups or _LOOKUPS.get(spec.code, ()),
        derives=spec.derives or _derives(spec),
    )
