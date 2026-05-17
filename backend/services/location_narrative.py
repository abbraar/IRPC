"""Deterministic EN/AR narrative templates for manual location analysis fallback."""

from __future__ import annotations

from models import (
    InfrastructureOverlapDetail,
    LocationAnalysisInput,
    ProjectOverlapDetail,
    RecommendationItem,
    TemporalOverlapDetail,
)


def risk_level_label(level: str, language: str) -> str:
    labels = {
        "en": {"Low": "Low risk", "Medium": "Medium risk", "High": "High risk"},
        "ar": {"Low": "منخفض الخطورة", "Medium": "متوسط الخطورة", "High": "عالي الخطورة"},
    }
    return labels.get(language, labels["en"]).get(level, level)


def build_location_explanation(
    payload: LocationAnalysisInput,
    score: float,
    risk_level: str,
    infrastructure_overlaps: list[InfrastructureOverlapDetail],
    project_overlaps: list[ProjectOverlapDetail],
    temporal_overlaps: list[TemporalOverlapDetail],
    language: str,
) -> str:
    if language == "ar":
        lines = [
            "ملخص التقييم",
            (
                f"تم تصنيف هذا الموقع المُدخل يدويًا على أنه {risk_level_label(risk_level, 'ar')} "
                f"(درجة الخطورة {score}/100) لحفر بعمق {payload.depth} متر ونطاق عمل {payload.work_radius} متر."
            ),
            "",
            "سجل التعارضات",
        ]
        if infrastructure_overlaps:
            top = sorted(infrastructure_overlaps, key=lambda x: (x.severity != "High", x.distance_meters))[0]
            lines.append(
                f"- البنية التحتية: تم اكتشاف {len(infrastructure_overlaps)} تعارض/تعارضات. أقرب أصل مهم هو "
                f"{top.type} بدرجة أهمية {top.criticality} وعلى بعد {top.distance_meters} متر."
            )
            if top.depth_conflict:
                lines.append(
                    f"- العمق: عمق الحفر المُدخل أكبر من أو قريب من عمق الأصل القريب ({top.asset_depth} متر)."
                )
        else:
            lines.append("- البنية التحتية: لم يتم اكتشاف تعارض مع نطاق تأثير الأصول المسجلة.")
        if project_overlaps:
            top_project = project_overlaps[0]
            lines.append(
                f"- المشاريع: تم اكتشاف {len(project_overlaps)} تعارض/تعارضات مع مشاريع قريبة، منها "
                f"{top_project.name} على بعد {top_project.distance_meters} متر."
            )
        if temporal_overlaps:
            top_temporal = max(temporal_overlaps, key=lambda x: x.overlap_days)
            lines.append(
                f"- الجدول الزمني: تم اكتشاف {len(temporal_overlaps)} تعارض/تعارضات زمنية. أطول تعارض "
                f"مدته {top_temporal.overlap_days} يومًا مع {top_temporal.name} "
                f"من {top_temporal.start_date} إلى {top_temporal.end_date}."
            )
        lines.extend(
            [
                "",
                "إرشادات المحلل",
                "- هذه نتيجة فحص مكتبي باستخدام بيانات افتراضية. تبقى سجلات ملاك المرافق، والكشف الميداني، والتصاريح، والمراجعة الهندسية هي المراجع المعتمدة.",
            ]
        )
        return "\n".join(lines)

    lines = [
        "ASSESSMENT SUMMARY",
        (
            f"This manually entered location is classified as {risk_level.upper()} Risk "
            f"(score {score}/100) for a {payload.depth}m deep excavation with a "
            f"{payload.work_radius}m work radius."
        ),
        "",
        "CONFLICT REGISTER",
    ]
    if infrastructure_overlaps:
        top = sorted(infrastructure_overlaps, key=lambda x: (x.severity != "High", x.distance_meters))[0]
        lines.append(
            f"- Infrastructure: {len(infrastructure_overlaps)} overlap(s). The closest priority asset is "
            f"{top.type} ({top.criticality}) at {top.distance_meters}m."
        )
        if top.depth_conflict:
            lines.append(
                f"- Depth: entered excavation depth is greater than or close to the nearby asset depth ({top.asset_depth}m)."
            )
    else:
        lines.append("- Infrastructure: no mapped asset influence-zone overlaps were detected.")
    if project_overlaps:
        top_project = project_overlaps[0]
        lines.append(
            f"- Projects: {len(project_overlaps)} nearby project overlap(s), including {top_project.name} "
            f"at {top_project.distance_meters}m."
        )
    if temporal_overlaps:
        top_temporal = max(temporal_overlaps, key=lambda x: x.overlap_days)
        lines.append(
            f"- Schedule: {len(temporal_overlaps)} temporal overlap(s). The longest overlap is "
            f"{top_temporal.overlap_days} days with {top_temporal.name} "
            f"from {top_temporal.start_date} to {top_temporal.end_date}."
        )
    lines.extend(
        [
            "",
            "ANALYST GUIDANCE",
            "- Treat this as a synthetic desk-screening result. Utility owner records, field locate, permits, and engineering review remain authoritative.",
        ]
    )
    return "\n".join(lines)


def build_location_recommendations(
    risk_level: str,
    infrastructure_overlaps: list[InfrastructureOverlapDetail],
    project_overlaps: list[ProjectOverlapDetail],
    temporal_overlaps: list[TemporalOverlapDetail],
    payload: LocationAnalysisInput,
    language: str,
) -> list[RecommendationItem]:
    recs: list[RecommendationItem] = []
    high_infra = [item for item in infrastructure_overlaps if item.severity == "High"]
    depth_conflicts = [item for item in infrastructure_overlaps if item.depth_conflict]
    combined_projects = [item for item in project_overlaps if item.has_temporal_overlap]

    if language == "ar":
        if risk_level == "High" or high_infra:
            recs.append(
                RecommendationItem(
                    action="يلزم مراجعة هندسية يدوية",
                    reasoning="تم اكتشاف عوامل خطورة عالية قرب الموقع المُدخل. يجب التحقق من سجلات المرافق، وموافقات ملاك الأصول، وضوابط الحفر قبل بدء العمل الميداني.",
                    priority="high",
                )
            )
        if high_infra or len(infrastructure_overlaps) >= 2:
            recs.append(
                RecommendationItem(
                    action="تقليل نطاق العمل",
                    reasoning="نطاق العمل المُدخل يتداخل مع مناطق تأثير البنية التحتية المسجلة. تقليل نطاق العمل يمكن أن يخفض التعرض الأفقي للمخاطر.",
                    priority="medium" if risk_level != "High" else "high",
                )
            )
            recs.append(
                RecommendationItem(
                    action="تغيير مسار منطقة الحفر",
                    reasoning="انقل نطاق الحفر بعيدًا عن ممر المرافق الأعلى أهمية إذا سمحت قيود التصميم بذلك.",
                    priority="medium",
                )
            )
        if depth_conflicts:
            recs.append(
                RecommendationItem(
                    action="تعديل عمق الحفر",
                    reasoning=f"العمق المُدخل ({payload.depth} متر) يصل إلى عمق أصول قريبة أو يقترب منه. يجب تأكيد العمق المطلوب أو استخدام كشف تدريجي/حفر استكشافي.",
                    priority="medium",
                )
            )
        if temporal_overlaps or combined_projects:
            recs.append(
                RecommendationItem(
                    action="إعادة جدولة فترة العمل",
                    reasoning="فترة العمل المُدخلة تتداخل مع نشاط مشاريع قريبة. تغيير نافذة العمل يمكن أن يقلل مخاطر الازدحام والتنسيق.",
                    priority="medium" if not combined_projects else "high",
                )
            )
        if not recs:
            recs.append(
                RecommendationItem(
                    action="المتابعة",
                    reasoning="لم يتم اكتشاف تعارض جوهري مع البنية التحتية أو المشاريع ضمن حدود الفحص الافتراضية. استمر في إجراءات التصريح والكشف القياسية.",
                    priority="low",
                )
            )
        elif risk_level == "Medium":
            recs.append(
                RecommendationItem(
                    action="المتابعة بحذر",
                    reasoning="الموقع ليس مرفوضًا تلقائيًا، لكن يوصى بتطبيق ضوابط تخفيف والتحقق من المرافق قبل الحفر.",
                    priority="medium",
                )
            )
        return recs[:5]

    if risk_level == "High" or high_infra:
        recs.append(
            RecommendationItem(
                action="Manual engineering review required",
                reasoning="High risk drivers were detected near the submitted location. Validate utility records, owner clearances, and excavation controls before field work.",
                priority="high",
            )
        )
    if high_infra or len(infrastructure_overlaps) >= 2:
        recs.append(
            RecommendationItem(
                action="Reduce work radius",
                reasoning="The entered work radius overlaps mapped infrastructure influence zones. Reducing the work envelope can lower horizontal exposure.",
                priority="medium" if risk_level != "High" else "high",
            )
        )
        recs.append(
            RecommendationItem(
                action="Reroute excavation area",
                reasoning="Shift the excavation footprint away from the highest-criticality utility corridor if design tolerances allow.",
                priority="medium",
            )
        )
    if depth_conflicts:
        recs.append(
            RecommendationItem(
                action="Adjust excavation depth",
                reasoning=f"The entered depth ({payload.depth}m) reaches or approaches nearby asset depth. Confirm required depth or use staged exposure/potholing.",
                priority="medium",
            )
        )
    if temporal_overlaps or combined_projects:
        recs.append(
            RecommendationItem(
                action="Reschedule work window",
                reasoning="The submitted schedule overlaps nearby project activity. Moving the work window can reduce congestion and coordination risk.",
                priority="medium" if not combined_projects else "high",
            )
        )
    if not recs:
        recs.append(
            RecommendationItem(
                action="Proceed",
                reasoning="No material infrastructure or project overlap was detected under the synthetic screening thresholds. Continue standard locate and permit checks.",
                priority="low",
            )
        )
    elif risk_level == "Medium":
        recs.append(
            RecommendationItem(
                action="Proceed with caution",
                reasoning="The location is not automatically blocked, but mitigation controls and utility verification are recommended before excavation.",
                priority="medium",
            )
        )
    return recs[:5]
