"""Reusable UI components (pure presentation, no business logic)."""
from __future__ import annotations

import streamlit as st


def page_header(title: str, subtitle: str = "") -> None:
    st.markdown(f"## {title}")
    if subtitle:
        st.caption(subtitle)
    st.divider()


def section_header(title: str) -> None:
    st.markdown(f"### {title}")


def stat_card(label: str, value, desc: str = "") -> None:
    st.metric(label=label, value=value, help=desc or None)


def discrepancy_badge(delta: int) -> str:
    if delta == 0:
        return "Balanced"
    if delta > 0:
        return f"+{delta} (overload)"
    return f"{delta} (underload)"


def wizard_stepper(steps: list[str], current: int) -> None:
    cols = st.columns(len(steps))
    for i, (col, label) in enumerate(zip(cols, steps)):
        with col:
            if i < current:
                marker = "[done]"
            elif i == current:
                marker = "[current]"
            else:
                marker = "[ ]"
            st.markdown(f"{marker} **{label}**" if i == current else f"{marker} {label}")
