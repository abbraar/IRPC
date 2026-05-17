"""Rule-based analysis for manually entered excavation coordinates."""

from __future__ import annotations

from datetime import date, timedelta
import math

from models import (
    ContributingFactor,
    HistoricalIncident,
    InfrastructureAsset,
    LocationAnalysisInput,
    LocationAnalysisResponse,
    Project,
    RecommendationItem,
)
from services.conflict_detection import haversine_m

NEIGHBORHOOD_POLYGON = [
    [24.82991436680011, 46.66972979804959],
    [24.833810953932122, 46.6791362811475],
    [24.826761313414863, 46.682807103819854],
    [24.822775263119926, 46.673302295114645],
]
MIN_LAT = 24.822775263119926
MAX_LAT = 24.833810953932122
MIN_LNG = 46.66972979804959
MAX_LNG = 46.682807103819854
NEIGHBORHOOD_CENTER = (
    sum(point[0] for point in NEIGHBORHOOD_POLYGON) / len(NEIGHBORHOOD_POLYGON),
    sum(point[1] for point in NEIGHBORHOOD_POLYGON) / len(NEIGHBORHOOD_POLYGON),
)


def _actual_lat_lon(payload: LocationAnalysisInput) -> tuple[float, float]:
    return payload.latitude, payload.longitude


def is_point_inside_neighborhood(latitude: float, longitude: float) -> bool:
    return MIN_LAT <= latitude <= MAX_LAT and MIN_LNG <= longitude <= MAX_LNG


def _clamp_to_neighborhood(lat: float, lon: float) -> tuple[float, float]:
    return min(MAX_LAT, max(MIN_LAT, lat)), min(MAX_LNG, max(MIN_LNG, lon))


def _neighborhood_context(is_inside: bool) -> dict:
    return {
        "name": "An Narjis District, Riyadh",
        "name_ar": "حي النرجس، الرياض",
        "is_inside_demo_area": is_inside,
        "boundary": NEIGHBORHOOD_POLYGON,
    }


def _offset_meters(lat: float, lon: float, dist_m: float, bearing_deg: float) -> tuple[float, float]:
    bearing = math.radians(bearing_deg)
    dlat = (dist_m * math.cos(bearing)) / 111_320.0
    dlon = (dist_m * math.sin(bearing)) / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def _local_synthetic_context(
    payload: LocationAnalysisInput,
) -> tuple[list[InfrastructureAsset], list[Project], list[HistoricalIncident]]:
    """Deterministic local context around any submitted coordinate for demo continuity."""
    submitted_lat, submitted_lon = _actual_lat_lon(payload)
    if is_point_inside_neighborhood(submitted_lat, submitted_lon):
        lat, lon = submitted_lat, submitted_lon
    else:
        lat, lon = NEIGHBORHOOD_CENTER
    asset_templates = [
        ("CTX-AST-GAS", "Gas Pipeline", 8.0, 35.0, 1.65, "High", 14.0, 96.0),
        ("CTX-AST-WATER", "Water Pipe", 18.0, 118.0, 2.1, "Medium", 10.0, 72.0),
        ("CTX-AST-ELEC", "Electrical Cable", 34.0, 240.0, 1.35, "High", 9.0, 91.0),
        ("CTX-AST-TEL", "Telecom Line", 58.0, 315.0, 1.0, "Low", 7.0, 45.0),
    ]
    context_assets: list[InfrastructureAsset] = []
    for asset_id, type_name, dist, bearing, depth, criticality, influence, sensitivity in asset_templates:
        asset_lat, asset_lon = _offset_meters(lat, lon, dist, bearing)
        asset_lat, asset_lon = _clamp_to_neighborhood(asset_lat, asset_lon)
        context_assets.append(
            InfrastructureAsset(
                asset_id=asset_id,
                type=type_name,  # type: ignore[arg-type]
                latitude=round(asset_lat, 6),
                longitude=round(asset_lon, 6),
                depth=depth,
                criticality=criticality,  # type: ignore[arg-type]
                influence_radius=influence,
                sensitivity_score=sensitivity,
            )
        )

    project_templates = [
        ("CTX-PRJ-ROAD", "Ongoing Road Project", 22.0, 70.0, 26.0, -2, 24, "Active"),
        ("CTX-PRJ-MAINT", "Water Network Maintenance", 48.0, 210.0, 22.0, 8, 30, "Active"),
        ("CTX-PRJ-TELECOM", "Telecom Duct Survey", 86.0, 305.0, 20.0, 18, 38, "Planning"),
    ]
    context_projects: list[Project] = []
    for project_id, name, dist, bearing, radius, start_offset, duration, status in project_templates:
        project_lat, project_lon = _offset_meters(lat, lon, dist, bearing)
        project_lat, project_lon = _clamp_to_neighborhood(project_lat, project_lon)
        start = payload.start_date + timedelta(days=start_offset)
        context_projects.append(
            Project(
                project_id=project_id,
                name=name,
                latitude=round(project_lat, 6),
                longitude=round(project_lon, 6),
                radius_meters=radius,
                start_date=start,
                end_date=start + timedelta(days=duration),
                status=status,
            )
        )

    incident_templates = [
        ("CTX-INC-GAS", "Third-party strike", "High", "Gas Pipeline", 38.0, 150.0),
        ("CTX-INC-UNKNOWN", "Unknown utility", "Medium", "Electrical Cable", 92.0, 260.0),
    ]
    context_incidents: list[HistoricalIncident] = []
    for incident_id, incident_type, severity, asset_type, dist, bearing in incident_templates:
        inc_lat, inc_lon = _offset_meters(lat, lon, dist, bearing)
        inc_lat, inc_lon = _clamp_to_neighborhood(inc_lat, inc_lon)
        context_incidents.append(
            HistoricalIncident(
                incident_id=incident_id,
                latitude=round(inc_lat, 6),
                longitude=round(inc_lon, 6),
                incident_type=incident_type,
                severity=severity,  # type: ignore[arg-type]
                related_asset_type=asset_type,
            )
        )
    return context_assets, context_projects, context_incidents


def _overlap_days(a_start: date, a_end: date, b_start: date, b_end: date) -> int:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start > end:
        return 0
    return (end - start).days + 1


def _level(score: float) -> str:
    if score <= 30:
        return "Low"
    if score <= 70:
        return "Medium"
    return "High"


def _risk_level_label(level: str, language: str) -> str:
    labels = {
        "en": {"Low": "Low risk", "Medium": "Medium risk", "High": "High risk"},
        "ar": {"Low": "منخفض الخطورة", "Medium": "متوسط الخطورة", "High": "عالي الخطورة"},
    }
    return labels.get(language, labels["en"]).get(level, level)


def _severity_from_asset(asset: InfrastructureAsset, distance_m: float, payload: LocationAnalysisInput) -> str:
    depth_conflict = payload.depth >= asset.depth - 0.35
    very_close = distance_m <= max(5.0, payload.work_radius * 0.45)
    if asset.criticality == "High" and depth_conflict and very_close:
        return "High"
    if asset.criticality == "High" or depth_conflict or distance_m <= payload.work_radius:
        return "Medium"
    return "Low"


def _severity_from_project(spatial: bool, temporal_days: int) -> str:
    if spatial and temporal_days >= 14:
        return "High"
    if spatial and temporal_days > 0:
        return "Medium"
    if spatial:
        return "Medium"
    if temporal_days > 0:
        return "Low"
    return "Low"


def _mk_factor(
    factor: str,
    display_name: str,
    category: str,
    points: float,
    detail: str,
    total: float,
) -> ContributingFactor:
    return ContributingFactor(
        factor=factor,
        display_name=display_name,
        category=category,  # type: ignore[arg-type]
        weight_contribution=round(points, 2),
        pct_of_composite=round((points / total) * 100, 1) if total > 0 else 0.0,
        detail=detail,
    )


def analyze_manual_location(
    payload: LocationAnalysisInput,
    infrastructure: list[InfrastructureAsset],
    projects: list[Project],
    incidents: list[HistoricalIncident],
) -> LocationAnalysisResponse:
    lat, lon = _actual_lat_lon(payload)
    is_inside_demo_area = is_point_inside_neighborhood(lat, lon)
    context_assets, context_projects, context_incidents = _local_synthetic_context(payload)
    analysis_infrastructure = [*context_assets, *infrastructure]
    analysis_projects = [*context_projects, *projects]
    analysis_incidents = [*context_incidents, *incidents]

    infrastructure_overlaps: list[dict] = []
    nearby_assets = 0
    context_asset_ids: set[str] = {asset.asset_id for asset in context_assets}
    for asset in analysis_infrastructure:
        distance = haversine_m(lat, lon, asset.latitude, asset.longitude)
        threshold = payload.work_radius + asset.influence_radius
        if distance <= threshold + 30:
            nearby_assets += 1
        if distance <= threshold + 95:
            context_asset_ids.add(asset.asset_id)
        if distance <= threshold:
            depth_conflict = payload.depth >= asset.depth - 0.35
            severity = _severity_from_asset(asset, distance, payload)
            infrastructure_overlaps.append(
                {
                    "asset_id": asset.asset_id,
                    "type": asset.type,
                    "latitude": asset.latitude,
                    "longitude": asset.longitude,
                    "distance_meters": round(distance, 2),
                    "asset_depth": asset.depth,
                    "criticality": asset.criticality,
                    "influence_radius": asset.influence_radius,
                    "sensitivity_score": asset.sensitivity_score,
                    "depth_conflict": depth_conflict,
                    "severity": severity,
                }
            )

    project_overlaps: list[dict] = []
    temporal_overlaps: list[dict] = []
    context_project_ids: set[str] = {project.project_id for project in context_projects}
    for project in analysis_projects:
        distance = haversine_m(lat, lon, project.latitude, project.longitude)
        spatial = distance <= payload.work_radius + project.radius_meters
        temporal_days = _overlap_days(payload.start_date, payload.end_date, project.start_date, project.end_date)
        severity = _severity_from_project(spatial, temporal_days)
        if distance <= payload.work_radius + project.radius_meters + 125:
            context_project_ids.add(project.project_id)
        if spatial:
            project_overlaps.append(
                {
                    "project_id": project.project_id,
                    "name": project.name,
                    "latitude": project.latitude,
                    "longitude": project.longitude,
                    "distance_meters": round(distance, 2),
                    "radius_meters": project.radius_meters,
                    "status": project.status,
                    "severity": severity,
                    "has_temporal_overlap": temporal_days > 0,
                    "overlap_days": temporal_days,
                }
            )
        if temporal_days > 0 and distance <= payload.work_radius + project.radius_meters + 45:
            temporal_overlaps.append(
                {
                    "project_id": project.project_id,
                    "name": project.name,
                    "start_date": project.start_date.isoformat(),
                    "end_date": project.end_date.isoformat(),
                    "overlap_days": temporal_days,
                    "spatial_overlap": spatial,
                    "severity": severity,
                }
            )

    incident_count = 0
    context_incident_ids: set[str] = {incident.incident_id for incident in context_incidents}
    for incident in analysis_incidents:
        if haversine_m(lat, lon, incident.latitude, incident.longitude) <= 150:
            incident_count += 1
            context_incident_ids.add(incident.incident_id)

    context_infrastructure = [
        asset for asset in analysis_infrastructure if asset.asset_id in context_asset_ids
    ][:16]
    context_projects = [
        project for project in analysis_projects if project.project_id in context_project_ids
    ][:10]
    context_incidents = [
        incident for incident in analysis_incidents if incident.incident_id in context_incident_ids
    ][:8]

    high_infra = sum(1 for item in infrastructure_overlaps if item["severity"] == "High")
    med_infra = sum(1 for item in infrastructure_overlaps if item["severity"] == "Medium")
    high_projects = sum(1 for item in project_overlaps if item["severity"] == "High")
    combined_project = sum(1 for item in project_overlaps if item["has_temporal_overlap"])

    infra_points = min(34.0, high_infra * 13 + med_infra * 6 + len(infrastructure_overlaps) * 2)
    depth_points = min(10.0, (payload.depth / 5.0) * 10)
    radius_points = min(8.0, (payload.work_radius / 20.0) * 8)
    nearby_asset_points = min(8.0, nearby_assets * 1.4)
    incident_points = min(10.0, incident_count * 2.2)
    project_spatial_points = min(10.0, len(project_overlaps) * 3.2 + high_projects * 2.5)
    temporal_points = min(10.0, len(temporal_overlaps) * 2.0 + sum(t["overlap_days"] for t in temporal_overlaps) * 0.12)
    combined_points = min(10.0, combined_project * 4.0)

    raw = (
        infra_points
        + depth_points
        + radius_points
        + nearby_asset_points
        + incident_points
        + project_spatial_points
        + temporal_points
        + combined_points
    )
    score = round(max(0.0, min(100.0, raw)), 1)
    risk_level = _level(score)
    total = max(raw, 0.01)
    factors = [
        _mk_factor("manual_infrastructure_overlap", "Infrastructure overlap", "Buried utilities", infra_points, f"{len(infrastructure_overlaps)} infrastructure overlap(s), {high_infra} high severity.", total),
        _mk_factor("manual_depth", "Excavation depth", "Geometry", depth_points, f"Entered depth is {payload.depth}m.", total),
        _mk_factor("manual_radius", "Work radius", "Geometry", radius_points, f"Entered work radius is {payload.work_radius}m.", total),
        _mk_factor("manual_nearby_assets", "Nearby asset density", "Buried utilities", nearby_asset_points, f"{nearby_assets} mapped asset(s) near the work zone.", total),
        _mk_factor("manual_incidents", "Nearby incident history", "History", incident_points, f"{incident_count} previous incident(s) within 150m.", total),
        _mk_factor("manual_project_spatial", "Project spatial overlap", "Coordination", project_spatial_points, f"{len(project_overlaps)} project spatial overlap(s).", total),
        _mk_factor("manual_project_temporal", "Project temporal overlap", "Coordination", temporal_points, f"{len(temporal_overlaps)} schedule overlap(s).", total),
        _mk_factor("manual_combined_project_conflict", "Combined project conflict", "Coordination", combined_points, f"{combined_project} project(s) overlap in both space and time.", total),
    ]

    language = payload.language
    explanation = _build_location_explanation(
        payload,
        score,
        risk_level,
        infrastructure_overlaps,
        project_overlaps,
        temporal_overlaps,
        language,
    )
    recommendations = _build_location_recommendations(
        risk_level,
        infrastructure_overlaps,
        project_overlaps,
        temporal_overlaps,
        payload,
        language,
    )
    conflicts = [
        *[{"kind": "infrastructure", **item} for item in infrastructure_overlaps],
        *[{"kind": "project", **item} for item in project_overlaps],
        *[{"kind": "temporal", **item} for item in temporal_overlaps],
    ]
    confidence = min(0.92, max(0.5, 0.55 + min(0.25, nearby_assets * 0.025) + min(0.12, len(conflicts) * 0.015)))

    return LocationAnalysisResponse(
        input=payload,
        risk_score=score,
        risk_level=risk_level,  # type: ignore[arg-type]
        risk_level_label=_risk_level_label(risk_level, language),
        is_risky=risk_level != "Low",
        conflicts=conflicts,
        context_infrastructure=context_infrastructure,
        context_projects=context_projects,
        context_incidents=context_incidents,
        neighborhood_context=_neighborhood_context(is_inside_demo_area),
        project_overlaps=project_overlaps,
        infrastructure_overlaps=infrastructure_overlaps,
        temporal_overlaps=temporal_overlaps,
        explanation=explanation,
        recommendations=recommendations,
        confidence_score=round(confidence, 2),
        contributing_factors=factors,
    )


def _build_location_explanation(
    payload: LocationAnalysisInput,
    score: float,
    risk_level: str,
    infrastructure_overlaps: list[dict],
    project_overlaps: list[dict],
    temporal_overlaps: list[dict],
    language: str,
) -> str:
    if language == "ar":
        lines = [
            "ملخص التقييم",
            (
                f"تم تصنيف هذا الموقع المُدخل يدويًا على أنه {_risk_level_label(risk_level, 'ar')} "
                f"(درجة الخطورة {score}/100) لحفر بعمق {payload.depth} متر ونطاق عمل {payload.work_radius} متر."
            ),
            "",
            "سجل التعارضات",
        ]
        if infrastructure_overlaps:
            top = sorted(infrastructure_overlaps, key=lambda x: (x["severity"] != "High", x["distance_meters"]))[0]
            lines.append(
                f"- البنية التحتية: تم اكتشاف {len(infrastructure_overlaps)} تعارض/تعارضات. أقرب أصل مهم هو "
                f"{top['type']} بدرجة أهمية {top['criticality']} وعلى بعد {top['distance_meters']} متر."
            )
            if top["depth_conflict"]:
                lines.append(
                    f"- العمق: عمق الحفر المُدخل أكبر من أو قريب من عمق الأصل القريب ({top['asset_depth']} متر)."
                )
        else:
            lines.append("- البنية التحتية: لم يتم اكتشاف تعارض مع نطاق تأثير الأصول المسجلة.")
        if project_overlaps:
            top_project = project_overlaps[0]
            lines.append(
                f"- المشاريع: تم اكتشاف {len(project_overlaps)} تعارض/تعارضات مع مشاريع قريبة، منها "
                f"{top_project['name']} على بعد {top_project['distance_meters']} متر."
            )
        if temporal_overlaps:
            top_temporal = max(temporal_overlaps, key=lambda x: x["overlap_days"])
            lines.append(
                f"- الجدول الزمني: تم اكتشاف {len(temporal_overlaps)} تعارض/تعارضات زمنية. أطول تعارض "
                f"مدته {top_temporal['overlap_days']} يومًا مع {top_temporal['name']} "
                f"من {top_temporal['start_date']} إلى {top_temporal['end_date']}."
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
        top = sorted(infrastructure_overlaps, key=lambda x: (x["severity"] != "High", x["distance_meters"]))[0]
        lines.append(
            f"- Infrastructure: {len(infrastructure_overlaps)} overlap(s). The closest priority asset is "
            f"{top['type']} ({top['criticality']}) at {top['distance_meters']}m."
        )
        if top["depth_conflict"]:
            lines.append(
                f"- Depth: entered excavation depth is greater than or close to the nearby asset depth ({top['asset_depth']}m)."
            )
    else:
        lines.append("- Infrastructure: no mapped asset influence-zone overlaps were detected.")
    if project_overlaps:
        top_project = project_overlaps[0]
        lines.append(
            f"- Projects: {len(project_overlaps)} nearby project overlap(s), including {top_project['name']} "
            f"at {top_project['distance_meters']}m."
        )
    if temporal_overlaps:
        top_temporal = max(temporal_overlaps, key=lambda x: x["overlap_days"])
        lines.append(
            f"- Schedule: {len(temporal_overlaps)} temporal overlap(s). The longest overlap is "
            f"{top_temporal['overlap_days']} days with {top_temporal['name']} "
            f"from {top_temporal['start_date']} to {top_temporal['end_date']}."
        )
    lines.extend(
        [
            "",
            "ANALYST GUIDANCE",
            "- Treat this as a synthetic desk-screening result. Utility owner records, field locate, permits, and engineering review remain authoritative.",
        ]
    )
    return "\n".join(lines)


def _build_location_recommendations(
    risk_level: str,
    infrastructure_overlaps: list[dict],
    project_overlaps: list[dict],
    temporal_overlaps: list[dict],
    payload: LocationAnalysisInput,
    language: str,
) -> list[RecommendationItem]:
    recs: list[RecommendationItem] = []
    high_infra = [item for item in infrastructure_overlaps if item["severity"] == "High"]
    depth_conflicts = [item for item in infrastructure_overlaps if item["depth_conflict"]]
    combined_projects = [item for item in project_overlaps if item["has_temporal_overlap"]]

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
