from __future__ import annotations

import streamlit as st


CUSTOM_CSS = """
<style>
:root {
    --aseg-navy: #00304F;
    --aseg-orange: #FF5E12;
    --aseg-orange-soft: #FF7D42;
    --aseg-charcoal: #362D32;
}

.block-container {
    padding-top: 1.4rem;
    padding-bottom: 2rem;
    max-width: 1500px;
}

h1, h2, h3 {
    color: var(--aseg-navy);
}

[data-testid="stMetric"] {
    border: 1px solid rgba(0, 48, 79, 0.14);
    border-radius: 12px;
    padding: 0.8rem 1rem;
    background: #FFFFFF;
}

[data-testid="stSidebar"] {
    border-right: 1px solid rgba(0, 48, 79, 0.12);
}

.model-note {
    border-left: 4px solid var(--aseg-orange);
    background: rgba(255, 94, 18, 0.06);
    padding: 0.8rem 1rem;
    border-radius: 8px;
    margin: 0.75rem 0 1rem 0;
}

.status-ok {
    border-left: 4px solid #1f7a46;
    background: rgba(31, 122, 70, 0.07);
    padding: 0.75rem 1rem;
    border-radius: 8px;
}
</style>
"""


def apply_styles() -> None:
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
