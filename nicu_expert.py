import io
import re
from typing import Any, Dict, List

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

# ==========================================
# 1. CLINICAL LOGIC ENGINE
# ==========================================

class NicuExpertSystem:
    """IAFH NICU Local Clinical Expert System."""

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

        weight_kg = current_weight_grams / 1000 if current_weight_grams else 0
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
                milk_rate_ml_hr = volume / every if every > 0 else 0
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
            "status": status,
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
        <h3 style="color:#00c897; margin-bottom: 4px;">SITUATION</h3>
        <p>Patient <b>{name}</b> | GA <b>{ga_w}w {ga_d}d</b> | Room <b>{patient.get('room','N/A')}</b> | Acuity: <b>{acuity}</b><br>
        Recent Events: {recent_events or 'None reported'}</p>
        """

        background_html = f"""
        <h3 style="color:#4da6ff; margin-bottom: 4px;">BACKGROUND</h3>
        <p>
            DOL: {dol}<br>
            Diagnosis: {diagnoses_str}<br>
            Birth Weight: {birth_wt} g | Current Weight: {curr_wt} g ({weight_text})<br>
            Maternal History: {patient.get('maternalHistory', 'Unremarkable')}
        </p>
        """

        assessment_html = f"""
        <h3 style="color:#ffd633; margin-bottom: 4px;">ASSESSMENT</h3>
        <ul>
            <li>Respiratory Support: {resp.get('supportType', 'Room Air')} ({resp.get('details', 'N/A')})</li>
            <li>Feeding & Milk: {fluids.get('milkDetails', 'N/A')} - {fluids.get('milkAmountMl', 'N/A')}</li>
            <li>Active Lines: {lines_str if lines_str else 'None'}</li>
            <li>Current Meds: {meds or 'None'}</li>
            <li>Labs & Imaging: {labs or 'None pending/reported'}</li>
        </ul>
        """

        recommendation_html = f"""
        <h3 style="color:#00d26a; margin-bottom: 4px;">RECOMMENDATION</h3>
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


# ==========================================
# 2. STREAMLIT USER INTERFACE
# ==========================================

def main():
    st.set_page_config(
        page_title="NICU Expert System",
        page_icon="👶",
        layout="wide"
    )

    st.title("👶 IAFH NICU Clinical Expert System")
    st.caption("Offline Clinical Decision Support & SBAR Handoff Tool")

    tabs = st.tabs(["📊 GIR Calculator", "📋 SBAR Handoff", "📑 Discharge Summary"])

    # ----------------------------------------
    # TAB 1: GIR CALCULATOR
    # ----------------------------------------
    with tabs[0]:
        st.header("Glucose Infusion Rate (GIR) Calculator")
        
        col1, col2 = st.columns(2)

        with col1:
            weight_g = st.number_input("Current Weight (grams)", min_value=100.0, max_value=8000.0, value=1200.0, step=50.0)
            ivf_rate = st.number_input("IVF Rate (mL/hr)", min_value=0.0, max_value=50.0, value=4.0, step=0.1)
            ivf_details = st.selectbox("IVF Fluid Type", ["D10W", "D5W", "D7.5W", "D12.5W", "D15W"], index=0)

        with col2:
            tpn_type = st.selectbox("TPN Type", ["None", "Starter TPN", "Custom TPN"], index=0)
            milk_amount = st.text_input("Enteral Milk Amount (e.g., '6 mL q3h' or '2 mL/h')", value="6 mL q3h")

        if st.button("Calculate GIR", type="primary"):
            res = NicuExpertSystem.calculate_gir(
                current_weight_grams=weight_g,
                ivf_rate_ml_hr=ivf_rate,
                ivf_details=ivf_details,
                tpn_type=tpn_type,
                milk_amount_ml=milk_amount
            )

            st.divider()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Weight (kg)", f"{res['weightKg']:.2f}")
            m2.metric("Parenteral GIR", f"{res['parenteralGir']:.1f} mg/kg/min")
            m3.metric("Enteral GIR", f"{res['enteralGir']:.1f} mg/kg/min")
            m4.metric("Total GIR", f"{res['totalGir']:.1f} mg/kg/min")

            if res['status'] == "Within Target":
                st.success(f"Status: **{res['status']}** (Normal target: 4-8 mg/kg/min)")
            else:
                st.warning(f"Status: **{res['status']}** (Normal target: 4-8 mg/kg/min)")

            st.markdown(res['aiInsights'], unsafe_allow_html=True)

    # ----------------------------------------
    # TAB 2: SBAR HANDOFF
    # ----------------------------------------
    with tabs[1]:
        st.header("SBAR Handoff Generator")

        with st.form("sbar_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                p_name = st.text_input("Patient Name / ID", value="Baby John")
                mrn = st.text_input("MRN", value="123456")
                room = st.text_input("Room/Bed", value="NICU Bed 04")
            with c2:
                ga_w = st.number_input("Gestational Age (Weeks)", min_value=22, max_value=42, value=30)
                ga_d = st.number_input("Gestational Age (Days)", min_value=0, max_value=6, value=2)
                dol = st.number_input("Day of Life (DOL)", min_value=1, max_value=300, value=15)
            with c3:
                birth_wt = st.number_input("Birth Weight (g)", value=1200)
                curr_wt = st.number_input("Current Weight (g)", value=1250)
                acuity = st.selectbox("Acuity Level", NicuExpertSystem.CLINICAL_OPTIONS["acuity_levels"])

            st.subheader("Clinical Status")
            col_a, col_b = st.columns(2)
            with col_a:
                diagnoses = st.multiselect("Diagnoses", NicuExpertSystem.CLINICAL_OPTIONS["common_diagnoses"], default=["Prematurity", "Respiratory Distress Syndrome (RDS)"])
                resp_supp = st.selectbox("Respiratory Support", NicuExpertSystem.CLINICAL_OPTIONS["respiratory_support"], index=3)
                resp_details = st.text_input("Respiratory Settings", value="CPAP 5 cmH2O, FiO2 21%")
                lines = st.multiselect("Active Lines", NicuExpertSystem.CLINICAL_OPTIONS["line_types"], default=["Peripheral IV (PIV)"])
            
            with col_b:
                feed_type = st.selectbox("Feeding Type", NicuExpertSystem.CLINICAL_OPTIONS["feeding_types"], index=0)
                milk_details = st.text_input("Milk / Feeding Details", value="6 mL q3h")
                meds = st.text_area("Medications", value="Caffeine Citrate 5mg IV daily")
                labs = st.text_area("Recent Labs/Imaging", value="CBC normal, Bilirubin 6.5 mg/dL")

            recent_events = st.text_area("Recent Events / Concerns", value="Occipital scalp swelling noted today.")

            submit_sbar = st.form_submit_button("Generate SBAR Handoff", type="primary")

        if submit_sbar:
            patient_data = {
                "name": p_name,
                "mrn": mrn,
                "room": room,
                "gestationalAgeWeeks": ga_w,
                "gestationalAgeDays": ga_d,
                "dayOfLife": dol,
                "birthWeight": birth_wt,
                "currentWeight": curr_wt,
                "acuityLevel": acuity,
                "diagnoses": diagnoses,
                "recentEvents": recent_events,
                "respiratory": {"supportType": resp_supp, "details": resp_details},
                "fluidsNutrition": {"milkDetails": feed_type, "milkAmountMl": milk_details},
                "lines": lines,
                "medications": meds,
                "labs": labs,
            }

            sbar_res = NicuExpertSystem.generate_sbar_handoff(patient_data)

            # Display Alerts
            if sbar_res["safetyAlerts"]:
                st.error("🚨 **SAFETY ALERTS**")
                for alert in sbar_res["safetyAlerts"]:
                    st.write(f"- {alert}")

            # Display Verbal Script
            st.markdown(sbar_res["verbalScript"], unsafe_allow_html=True)

            if sbar_res["aiCritiqueAndRecommendations"]:
                st.markdown(sbar_res["aiCritiqueAndRecommendations"], unsafe_allow_html=True)

            # PDF Download
            pdf_bytes = NicuExpertSystem.generate_pdf_report(patient_data, sbar_res)
            st.download_button(
                label="📥 Download SBAR PDF Report",
                data=pdf_bytes,
                file_name=f"SBAR_{p_name.replace(' ', '_')}.pdf",
                mime="application/pdf"
            )

    # ----------------------------------------
    # TAB 3: DISCHARGE SUMMARY
    # ----------------------------------------
    with tabs[2]:
        st.header("Discharge Summary Generator")
        
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            d_mrn = st.text_input("Patient MRN", value="123456", key="d_mrn")
            d_ga_w = st.number_input("GA Weeks", value=32, key="d_gaw")
            d_ga_d = st.number_input("GA Days", value=0, key="d_gad")
            d_birth = st.number_input("Birth Weight (g)", value=1400, key="d_bw")
        
        with col_d2:
            d_curr = st.number_input("Discharge Weight (g)", value=1850, key="d_cw")
            d_diags = st.multiselect("Final Diagnoses", NicuExpertSystem.CLINICAL_OPTIONS["common_diagnoses"], default=["Prematurity"], key="d_diag")
            d_resp = st.selectbox("Discharge Respiratory Status", NicuExpertSystem.CLINICAL_OPTIONS["respiratory_support"], index=0, key="d_resp")
            d_outcome = st.selectbox("Discharge Outcome", NicuExpertSystem.CLINICAL_OPTIONS["discharge_outcomes"], index=0)

        if st.button("Generate Summary"):
            p_summary_data = {
                "mrn": d_mrn,
                "gestationalAgeWeeks": d_ga_w,
                "gestationalAgeDays": d_ga_d,
                "birthWeight": d_birth,
                "currentWeight": d_curr,
                "diagnoses": d_diags,
                "respiratory": {"supportType": d_resp}
            }
            summary_text = NicuExpertSystem.generate_discharge_summary(p_summary_data, d_outcome)
            
            st.subheader("Generated Discharge Text")
            st.info(summary_text)


if __name__ == "__main__":
    main()
