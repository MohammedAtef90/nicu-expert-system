import io
import re
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer


class NicuExpertSystem:
    """IAFH NICU Local Clinical Expert System.

    Works completely offline.
    """

    # القوائم والخيارات القياسية للواجهة والنظام
    CLINICAL_OPTIONS = {
        "acuity_levels": ["Stable", "Moderate", "Critical", "Extreme Critical"],
        "respiratory_support": [
            "Room Air",
            "Nasal Cannula",
            "High Flow Nasal Cannula (HFNC)",
            "CPAP",
            "NIPPV",
            "Conventional Mechanical Ventilation (CMV)",
            "High-Frequency Oscillatory Ventilation (HFOV)",
        ],
        "feeding_types": [
            "Maternal Breast Milk (MBM)",
            "Donor Human Milk (DHM)",
            "Preterm Formula",
            "Fortified Breast Milk",
            "NPO (Nothing by mouth)",
        ],
        "line_types": [
            "Peripheral IV (PIV)",
            "PICC Line",
            "Umbilical Artery Catheter (UAC)",
            "Umbilical Vein Catheter (UVC)",
            "Central Venous Line (CVC)",
        ],
        "common_diagnoses": [
            "Prematurity",
            "Respiratory Distress Syndrome (RDS)",
            "Transient Tachypnea of the Newborn (TTN)",
            "Neonatal Sepsis (Rule Out)",
            "Hypoglycemia",
            "Hyperbilirubinemia",
            "Necrotizing Enterocolitis (NEC)",
            "Intraventricular Hemorrhage (IVH)",
            "Patent Ductus Arteriosus (PDA)",
        ],
        "discharge_outcomes": [
            "Home with Parents",
            "Transfer to Local Step-down Hospital",
            "Transfer to Tertiary/Quaternary Care Facility",
            "Discharged against medical advice (DAMA)",
        ],
    }

    @staticmethod
    def calculate_weight_diff_text(
        birth_weight: float, current_weight: float
    ) -> str:
        if not birth_weight:
            return "stable"

        diff = current_weight - birth_weight
        pct = (diff / birth_weight) * 100

        if diff > 0:
            return f"up {diff:.0f}g (+{pct:.1f}% from birth weight)"
        elif diff < 0:
            return f"down {abs(diff):.0f}g ({pct:.1f}% from birth weight)"

        return "at birth weight"

    @classmethod
    def calculate_gir(
        cls,
        current_weight_grams: float,
        ivf_rate_ml_hr: float,
        ivf_details: str,
        tpn_type: str,
        milk_amount_ml: str,
    ) -> Dict[str, Any]:

        weight_kg = current_weight_grams / 1000
        ivf_dextrose = 10.0

        if ivf_details:
            match = re.search(
                r"D(\d+(\.\d+)?)", ivf_details, re.IGNORECASE
            )
            if match:
                ivf_dextrose = float(match.group(1))

        if weight_kg > 0:
            parenteral_gir = (ivf_rate_ml_hr * ivf_dextrose) / (6 * weight_kg)
        else:
            parenteral_gir = 0

        milk_rate_ml_hr = 0
        enteral_gir = 0

        if milk_amount_ml:
            q_match = re.search(
                r"(\d+(\.\d+)?)\s*mL\s*q\s*(\d+)",
                milk_amount_ml,
                re.IGNORECASE,
            )

            if q_match:
                volume = float(q_match.group(1))
                every = float(q_match.group(3))
                milk_rate_ml_hr = volume / every
            else:
                hourly = re.search(
                    r"(\d+(\.\d+)?)\s*mL/h", milk_amount_ml, re.IGNORECASE
                )
                if hourly:
                    milk_rate_ml_hr = float(hourly.group(1))

            if weight_kg > 0:
                enteral_gir = (milk_rate_ml_hr * 7) / (6 * weight_kg)

        total_gir = parenteral_gir + enteral_gir

        if 4 <= parenteral_gir <= 8:
            status = "Within Target"
        elif parenteral_gir < 4:
            status = "Low"
        else:
            status = "High"

        insights = f"""
        <h3>NICU Clinical Assessment</h3>
        <ul>
            <li>Parenteral GIR: <b>{parenteral_gir:.1f} mg/kg/min</b></li>
            <li>Enteral GIR: <b>{enteral_gir:.1f} mg/kg/min</b></li>
            <li>Combined GIR: <b>{total_gir:.1f} mg/kg/min</b></li>
            <li>Status: <b>{status}</b></li>
        </ul>
        """

        return {
            "weightKg": weight_kg,
            "parenteralGir": parenteral_gir,
            "enteralGir": enteral_gir,
            "totalGir": total_gir,
            "aiInsights": insights,
        }

    @classmethod
    def generate_sbar_handoff(cls, patient: Dict[str, Any]) -> Dict[str, Any]:
        name = patient.get("name", "Baby")
        ga_w = patient.get("gestationalAgeWeeks", 30)
        ga_d = patient.get("gestationalAgeDays", 0)
        dol = patient.get("dayOfLife", 1)
        birth_wt = patient.get("birthWeight", 1200)
        curr_wt = patient.get("currentWeight", 1250)
        diagnoses = patient.get("diagnoses", [])
        recent_events = patient.get("recentEvents", "")
        acuity = patient.get("acuityLevel", "Stable")

        resp = patient.get("respiratory", {})
        fluids = patient.get("fluidsNutrition", {})
        lines = patient.get("lines", [])
        labs = patient.get("labs", "")
        meds = patient.get("medications", "")

        diagnoses_str = (
            ", ".join(diagnoses)
            if isinstance(diagnoses, list)
            else str(diagnoses)
        )
        lines_str = ", ".join(lines) if isinstance(lines, list) else str(lines)

        weight_text = cls.calculate_weight_diff_text(birth_wt, curr_wt)

        safety_alerts = []
        critique_items = []

        if ga_w < 32 or birth_wt < 1500:
            safety_alerts.append(
                "High risk for Metabolic Bone Disease of Prematurity."
            )

        if ga_w < 34:
            safety_alerts.append("Risk for Necrotizing Enterocolitis (NEC).")

            if ga_w < 28:
                hazard = "Peak NEC window DOL 20-30"
                inside = 20 <= dol <= 30
            elif ga_w < 32:
                hazard = "Peak NEC window DOL 14-21"
                inside = 14 <= dol <= 21
            else:
                hazard = "Peak NEC window DOL 7-14"
                inside = 7 <= dol <= 14

            if inside:
                safety_alerts.append(f"CRITICAL: {hazard}")

        if any(
            word in recent_events.lower()
            for word in ["occipital", "cephalohematoma", "scalp swelling"]
        ):
            safety_alerts.append("Possible subgaleal hemorrhage.")
            critique_items.append("Urgent assessment required.")

        situation_html = f"""
        <h2 style="color:#00c897;">SITUATION</h2>
        <p>Patient <b>{name}</b> | GA <b>{ga_w}w {ga_d}d</b> | Room <b>{patient.get('room','N/A')}</b> | Acuity: <b>{acuity}</b><br>
        Recent Events: {recent_events or 'None reported'}</p>
        """

        background_html = f"""
        <h2 style="color:#4da6ff;">BACKGROUND</h2>
        <p>
            DOL: {dol}<br>
            Diagnosis: {diagnoses_str}<br>
            Birth Weight: {birth_wt} g | Current Weight: {curr_wt} g ({weight_text})<br>
            Maternal History: {patient.get('maternalHistory', 'Unremarkable')}
        </p>
        """

        assessment_html = f"""
        <h2 style="color:#ffd633;">ASSESSMENT</h2>
        <ul>
            <li>Respiratory Support: {resp.get('supportType', 'Room Air')} ({resp.get('details', 'N/A')})</li>
            <li>Feeding & Milk: {fluids.get('milkDetails', 'N/A')} - {fluids.get('milkAmountMl', 'N/A')}</li>
            <li>Active Lines: {lines_str if lines_str else 'None'}</li>
            <li>Current Meds: {meds or 'None'}</li>
            <li>Labs & Imaging: {labs or 'None pending/reported'}</li>
        </ul>
        """

        recommendation_html = f"""
        <h2 style="color:#00d26a;">RECOMMENDATION</h2>
        <ul>
            <li>Advance enteral feeding as tolerated.</li>
            <li>{"Start serial head circumference monitoring." if "occipital" in recent_events.lower() else "Continue strict intake/output monitoring."}</li>
            <li>Verify planned laboratory investigations and current medication doses.</li>
        </ul>
        """

        verbal_script = (
            situation_html
            + background_html
            + assessment_html
            + recommendation_html
        )

        critique_html = ""
        if critique_items:
            critique_html = "<div style='color:red;'>"
            for item in critique_items:
                critique_html += f"<p>• {item}</p>"
            critique_html += "</div>"

        return {
            "verbalScript": verbal_script,
            "safetyAlerts": safety_alerts,
            "clinicalFocus": "Monitor respiratory support, line sites, and fluid balance.",
            "aiCritiqueAndRecommendations": critique_html,
        }

    @classmethod
    def generate_discharge_summary(
        cls, patient: Dict[str, Any], outcome: str
    ) -> str:
        ga_w = patient.get("gestationalAgeWeeks", 30)
        ga_d = patient.get("gestationalAgeDays", 0)
        birth = patient.get("birthWeight", 1200)
        current = patient.get("currentWeight", 1200)
        diagnoses = patient.get("diagnoses", [])

        diagnoses_text = (
            ", ".join(diagnoses)
            if isinstance(diagnoses, list)
            else str(diagnoses)
        )

        weight = cls.calculate_weight_diff_text(birth, current)

        return (
            f"This {ga_w}w {ga_d}d infant "
            f"(MRN: {patient.get('mrn','N/A')}) "
            f"was admitted with {diagnoses_text}. "
            f"Birth weight {birth} g. "
            f"Current weight {current} g ({weight}). "
            f"Respiratory status on discharge: {patient.get('respiratory', {}).get('supportType', 'Room Air')}. "
            f"The infant is clinically stable and discharged as: {outcome}."
        )

    @classmethod
    def generate_pdf_report(
        cls, patient: Dict[str, Any], sbar_data: Dict[str, Any] = None
    ) -> bytes:
        """Generates a clean PDF report for printing/downloading."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        story = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            name="TitleStyle",
            parent=styles["Heading1"],
            fontSize=18,
            textColor=colors.HexColor("#005b96"),
            spaceAfter=12,
        )

        alert_style = ParagraphStyle(
            name="AlertStyle",
            parent=styles["Normal"],
            textColor=colors.HexColor("#c0392b"),
            fontSize=10,
            spaceAfter=4,
        )

        section_styles = {
            "SITUATION": ParagraphStyle(
                "Sit",
                parent=styles["Heading2"],
                textColor=colors.HexColor("#008060"),
                spaceBefore=8,
                spaceAfter=4,
            ),
            "BACKGROUND": ParagraphStyle(
                "Bg",
                parent=styles["Heading2"],
                textColor=colors.HexColor("#005b96"),
                spaceBefore=8,
                spaceAfter=4,
            ),
            "ASSESSMENT": ParagraphStyle(
                "Ass",
                parent=styles["Heading2"],
                textColor=colors.HexColor("#b36b00"),
                spaceBefore=8,
                spaceAfter=4,
            ),
            "RECOMMENDATION": ParagraphStyle(
                "Rec",
                parent=styles["Heading2"],
                textColor=colors.HexColor("#007b25"),
                spaceBefore=8,
                spaceAfter=4,
            ),
        }

        # Header
        story.append(Paragraph("NICU Clinical Handoff Report", title_style))
        story.append(
            HRFlowable(
                width="100%",
                thickness=1.5,
                color=colors.HexColor("#005b96"),
                spaceAfter=10,
            )
        )

        if not sbar_data:
            sbar_data = cls.generate_sbar_handoff(patient)

        # Safety Alerts
        alerts = sbar_data.get("safetyAlerts", [])
        if alerts:
            story.append(
                Paragraph(
                    "<b>SAFETY ALERTS:</b>",
                    ParagraphStyle(
                        "AlertHead",
                        parent=styles["Heading3"],
                        textColor=colors.HexColor("#c0392b"),
                    ),
                )
            )
            for alert in alerts:
                story.append(Paragraph(f"&bull; {alert}", alert_style))
            story.append(Spacer(1, 8))

        # Patient Info
        name = patient.get("name", "Baby")
        ga_w = patient.get("gestationalAgeWeeks", 30)
        ga_d = patient.get("gestationalAgeDays", 0)
        dol = patient.get("dayOfLife", 1)
        birth_wt = patient.get("birthWeight", 1200)
        curr_wt = patient.get("currentWeight", 1250)
        diagnoses = patient.get("diagnoses", [])
        recent_events = patient.get("recentEvents", "None reported")

        resp = patient.get("respiratory", {})
        fluids = patient.get("fluidsNutrition", {})
        lines = patient.get("lines", [])
        lines_str = ", ".join(lines) if isinstance(lines, list) else str(lines)

        diagnoses_str = (
            ", ".join(diagnoses)
            if isinstance(diagnoses, list)
            else str(diagnoses)
        )
        weight_text = cls.calculate_weight_diff_text(birth_wt, curr_wt)

        # SITUATION
        story.append(Paragraph("SITUATION", section_styles["SITUATION"]))
        p_sit = (
            f"Patient: <b>{name}</b> | MRN: <b>{patient.get('mrn','N/A')}</b> | GA: <b>{ga_w}w {ga_d}d</b> | Room: <b>{patient.get('room', 'N/A')}</b> | Acuity: <b>{patient.get('acuityLevel', 'Stable')}</b><br/>"
            f"Recent Events: {recent_events}"
        )
        story.append(Paragraph(p_sit, styles["Normal"]))

        # BACKGROUND
        story.append(Paragraph("BACKGROUND", section_styles["BACKGROUND"]))
        p_bg = (
            f"Day of Life (DOL): <b>{dol}</b><br/>"
            f"Diagnosis: <b>{diagnoses_str}</b><br/>"
            f"Birth Weight: <b>{birth_wt} g</b> | Current Weight: <b>{curr_wt} g</b> ({weight_text})<br/>"
            f"Maternal History: <b>{patient.get('maternalHistory', 'Unremarkable')}</b>"
        )
        story.append(Paragraph(p_bg, styles["Normal"]))

        # ASSESSMENT
        story.append(Paragraph("ASSESSMENT", section_styles["ASSESSMENT"]))
        p_ass = (
            f"&bull; Respiratory Support: {resp.get('supportType', 'Room Air')} ({resp.get('details', 'N/A')})<br/>"
            f"&bull; Feeding & Milk: {fluids.get('milkDetails', 'N/A')} - {fluids.get('milkAmountMl', 'N/A')}<br/>"
            f"&bull; Active Lines: {lines_str if lines_str else 'None'}<br/>"
            f"&bull; Medications: {patient.get('medications', 'None')}<br/>"
            f"&bull; Labs/Imaging: {patient.get('labs', 'None')}"
        )
        story.append(Paragraph(p_ass, styles["Normal"]))

        # RECOMMENDATION
        story.append(
            Paragraph("RECOMMENDATION", section_styles["RECOMMENDATION"])
        )
        p_rec = (
            "&bull; Advance enteral feeding as tolerated.<br/>"
            f"&bull; {'Start serial head circumference monitoring.' if 'occipital' in recent_events.lower() else 'Continue strict intake/output monitoring.'}<br/>"
            "&bull; Verify planned laboratory investigations and current medication doses."
        )
        story.append(Paragraph(p_rec, styles["Normal"]))

        doc.build(story)
        pdf_data = buffer.getvalue()
        buffer.close()
        return pdf_data


if __name__ == "__main__":
    result = NicuExpertSystem.calculate_gir(
        current_weight_grams=1200,
        ivf_rate_ml_hr=4,
        ivf_details="D10W",
        tpn_type="None",
        milk_amount_ml="6 mL q3h",
    )
    print("GIR Test Result:", result)