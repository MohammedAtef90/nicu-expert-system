import streamlit as st
from nicu_expert import NicuExpertSystem

# استخراج القوائم القياسية من النظام الخبير
CLINICAL_OPTIONS = NicuExpertSystem.CLINICAL_OPTIONS

# إعداد الصفحة
st.set_page_config(
    page_title="NICU Expert System",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🏥 NICU Clinical Expert System")
st.markdown("Clinical Decision Support for Neonatal Intensive Care Unit")
st.divider()

# الشريط الجانبي: بيانات المريض
st.sidebar.title("Patient Information")

name = st.sidebar.text_input("Patient Name", "Baby")
room = st.sidebar.text_input("Room", "A-1")
mrn = st.sidebar.text_input("MRN", "10001")

acuity_level = st.sidebar.selectbox(
    "Acuity Level",
    options=CLINICAL_OPTIONS["acuity_levels"],
    index=0,
)

ga_weeks = st.sidebar.number_input(
    "Gestational Age (Weeks)", min_value=22, max_value=42, value=30
)

ga_days = st.sidebar.number_input(
    "Additional Days", min_value=0, max_value=6, value=0
)

dol = st.sidebar.number_input("Day of Life", min_value=1, value=1)

birth_weight = st.sidebar.number_input("Birth Weight (g)", value=1200)

current_weight = st.sidebar.number_input("Current Weight (g)", value=1250)

selected_diagnoses = st.sidebar.multiselect(
    "Diagnoses",
    options=CLINICAL_OPTIONS["common_diagnoses"],
    default=["Prematurity"],
)

recent_events = st.sidebar.text_area("Recent Events", "")

maternal_history = st.sidebar.text_area("Maternal History", "Unremarkable")

# --- الخيارات الكلينيكية المتقدمة المعتمدة على CLINICAL_OPTIONS ---
st.sidebar.subheader("Clinical Status & Lines")

respiratory_type = st.sidebar.selectbox(
    "Respiratory Support",
    options=CLINICAL_OPTIONS["respiratory_support"],
    index=3,  # Default: CPAP
)

respiratory_details = st.sidebar.text_input(
    "Respiratory Settings/Details", "PEEP 5 cmH2O, FiO2 21%"
)

milk_type = st.sidebar.selectbox(
    "Feeding / Milk Type",
    options=CLINICAL_OPTIONS["feeding_types"],
    index=0,  # Default: Maternal Breast Milk (MBM)
)

milk_amount = st.sidebar.text_input("Milk Amount/Schedule", "6 mL q3h")

active_lines = st.sidebar.multiselect(
    "Active Lines",
    options=CLINICAL_OPTIONS["line_types"],
    default=["PICC Line"],
)

labs_summary = st.sidebar.text_area(
    "Recent Labs & Imaging", "CBC normal, CRP negative, Chest X-ray clear"
)

medications = st.sidebar.text_area(
    "Current Medications", "Ampicillin, Gentamicin, Caffeine Citrate"
)

# تجميع كافة بيانات المريض
patient = {
    "name": name,
    "room": room,
    "mrn": mrn,
    "acuityLevel": acuity_level,
    "gestationalAgeWeeks": ga_weeks,
    "gestationalAgeDays": ga_days,
    "dayOfLife": dol,
    "birthWeight": birth_weight,
    "currentWeight": current_weight,
    "diagnoses": selected_diagnoses,
    "recentEvents": recent_events,
    "maternalHistory": maternal_history,
    "respiratory": {
        "supportType": respiratory_type,
        "details": respiratory_details,
    },
    "fluidsNutrition": {
        "milkDetails": milk_type,
        "milkAmountMl": milk_amount,
    },
    "lines": active_lines,
    "labs": labs_summary,
    "medications": medications,
}

# التبويبات (Tabs)
tab1, tab2, tab3, tab4 = st.tabs(
    [
        "GIR Calculator",
        "SBAR Handoff",
        "Discharge Summary",
        "🖨️ Print & Export PDF",
    ]
)

# Tab 1: حاسبة GIR
with tab1:
    st.header("Glucose Infusion Rate (GIR) Calculator")

    col1, col2 = st.columns(2)
    with col1:
        ivf_rate = st.number_input("IVF Rate (mL/hr)", value=4.0, step=0.1)
        ivf_details = st.text_input("IVF Details", "D10W")
    with col2:
        tpn_type = st.text_input("TPN Type", "None")
        milk_amount_input = st.text_input(
            "Milk Amount/Schedule", patient["fluidsNutrition"]["milkAmountMl"]
        )

    if st.button("Calculate GIR", type="primary"):
        gir_result = NicuExpertSystem.calculate_gir(
            current_weight_grams=current_weight,
            ivf_rate_ml_hr=ivf_rate,
            ivf_details=ivf_details,
            tpn_type=tpn_type,
            milk_amount_ml=milk_amount_input,
        )

        m1, m2, m3 = st.columns(3)
        m1.metric(
            "Parenteral GIR", f"{gir_result['parenteralGir']:.1f} mg/kg/min"
        )
        m2.metric("Enteral GIR", f"{gir_result['enteralGir']:.1f} mg/kg/min")
        m3.metric("Total GIR", f"{gir_result['totalGir']:.1f} mg/kg/min")

        st.markdown(gir_result["aiInsights"], unsafe_allow_html=True)

# Tab 2: تقرير SBAR
with tab2:
    st.header("SBAR Handoff Report")

    if st.button("Generate SBAR Handoff", type="primary"):
        st.session_state["sbar_data"] = NicuExpertSystem.generate_sbar_handoff(
            patient
        )

    if "sbar_data" in st.session_state:
        sbar_data = st.session_state["sbar_data"]

        if sbar_data.get("safetyAlerts"):
            st.error("⚠️ Safety Alerts")
            for alert in sbar_data["safetyAlerts"]:
                st.write(f"- {alert}")

        st.markdown(sbar_data["verbalScript"], unsafe_allow_html=True)

# Tab 3: ملخص الخروج
with tab3:
    st.header("Discharge Summary Generator")

    outcome = st.selectbox(
        "Discharge Outcome",
        options=CLINICAL_OPTIONS["discharge_outcomes"],
    )

    if st.button("Generate Discharge Summary"):
        summary = NicuExpertSystem.generate_discharge_summary(patient, outcome)
        st.text_area("Discharge Text", value=summary, height=150)

# Tab 4: صفحة الطباعة وتصدير الـ PDF
with tab4:
    st.header("🖨️ Patient Report Print & Export")
    st.info(
        "تأكد من إدخال وتحديث كافة بيانات المريض في الشريط الجانبي (Sidebar) قبل التصدير."
    )

    st.markdown("### 📋 ملخص البيانات المسجلة حالياً")

    # عرض البيانات داخل كارت أنيق ومنسق
    with st.container(border=True):
        col_a, col_b, col_c = st.columns(3)

        with col_a:
            st.markdown("##### 👤 الهوية والإقامة")
            st.markdown(
                f"""
            * **الاسم:** `{patient['name']}`
            * **الغرفة:** `{patient['room']}`
            * **الرقم الطبي (MRN):** `{patient['mrn']}`
            * **الحالة (Acuity):** `{patient['acuityLevel']}`
            """
            )

        with col_b:
            st.markdown("##### 👶 العمر والوزن")
            st.markdown(
                f"""
            * **العمر الرحمي:** `{patient['gestationalAgeWeeks']}w {patient['gestationalAgeDays']}d`
            * **يوم الحياة (DOL):** `DOL {patient['dayOfLife']}`
            * **الوزن الحالي:** `{patient['currentWeight']} g`
            * **الوزن عند الولادة:** `{patient['birthWeight']} g`
            """
            )

        with col_c:
            st.markdown("##### 🏥 الوضع السريري")
            st.markdown(
                f"""
            * **التشخيص:** `{', '.join(patient['diagnoses']) if patient['diagnoses'] else 'N/A'}`
            * **الدعم التنفسي:** `{patient['respiratory']['supportType']}`
            * **التغذية:** `{patient['fluidsNutrition']['milkDetails']}`
            * **الخطوط الوريدية:** `{', '.join(patient['lines']) if patient['lines'] else 'None'}`
            """
            )

    st.divider()

    if "sbar_data" in st.session_state:
        sbar_data_for_pdf = st.session_state["sbar_data"]
    else:
        sbar_data_for_pdf = NicuExpertSystem.generate_sbar_handoff(patient)

    pdf_bytes = NicuExpertSystem.generate_pdf_report(
        patient=patient, sbar_data=sbar_data_for_pdf
    )

    st.download_button(
        label="📄 طباعة / تحميل تقرير المريض (PDF)",
        data=pdf_bytes,
        file_name=f"NICU_Report_{patient['name'].replace(' ', '_')}_{patient['mrn']}.pdf",
        mime="application/pdf",
        type="primary",
        use_container_width=True,
    )
