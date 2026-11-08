# AURA PS1 — Demo walkthrough (about 5 minutes)

Start everything with `docker compose up --build`, then open http://localhost:5173.

1. **Overview** — the solution design (data → pipeline → engine → lender workflow), how each of
   the six PS1 points is covered, current coverage and the rollout plan.
2. **Valuation Studio** — value the pre-filled Pune / Baner apartment with a ₹60 lakh loan:
   - value, 90% range and confidence; the "Why this value" factors and their data sources;
   - LTV against the RBI cap, maximum eligible loan, risk band, and the route (desk valuation);
   - locality signals (government, geo-spatial, infrastructure, satellite, market trend) and comparables;
   - **Download PDF report**, then **Send to lender review queue**.
   - Try a **Villa** or **Retail Shop** (wider range, lower confidence) and **Jaipur** (outside coverage → physical inspection).
3. **Batch Valuation** — **Try with sample data**: 10 properties valued, routed and stored in well under a second.
4. **Review Queue** — record a decision on the case you created; see the physical-visits-avoided metric.
5. **Model & Accuracy** — AURA vs rate-card AVM vs guideline rates (MAPE, PPE10, PPE20), errors by segment, and how accuracy would be proven on real data.
6. **Data Sources** — how each source is collected, cleaned and merged; import `sample_comparables.csv`; search the Indore guideline-rate extract.

Swagger for the API: http://localhost:8000/docs

**Say clearly when presenting:** all data is synthetic; the numbers show the method, not real-market accuracy. AURA supports, and does not replace, the credit officer's decision.
