# LIBERA v5.2 illustrated manuscript

Deliverable: one editable DOCX containing the reviewed v5.2 manuscript and the four agreed results figures.

Design authority: the existing LIBERA manuscript structure and formal A4 style; preserve v5.2 prose, claims, units and source scope. Use black headings, Malgun Gothic text, restrained blue quantitative marks, readable tables, and numbered pages. No invented author or affiliation.

Main figures: final allocation heatmap in 6.2; two-panel TV-distance dot plot in 6.3; evidence/explanation/selection case diagram in 6.4; Fidelity L normalization direction reversal in 7.3.

Tables: retain original table 5 in the body; move tables 6–8 to supplementary tables A1–A3 and update cross-references. Keep tables 1–4 and 9–11 in the body, renumbering the latter 6–8. Put full D0/F0 raw and derived allocations and the control-relative heatmap in the appendix.

Figures: use deterministic plotting, 600 dpi PNG for insertion, editable SVG originals and CSV data. No uncertainty bars, significance marks, causal-effect labels, or aggregate error rates.

Runtime: the workspace loader is not exposed in this session. Resolve bundled executables against the installed runtime manifest at C:/Users/Insun/.cache/codex-runtimes/codex-primary-runtime/runtime.json. Python is dependencies/python/python.exe; Node is dependencies/node/bin/node.exe. Use those for all authoring.

Rendering: run the packaged render_docx.py first and inspect its logs. The manifest reports no bundled LibreOffice. If unavailable, use the existing isolated read-only Word COM renderer without touching running user documents, then bundled Poppler to generate every page PNG. Never use a desktop LibreOffice installation.

Final QA: inspect every page image, confirm the four agreed main figures plus appendix figure, verify all values against the frozen v5.2 source and completed-case data, update broken or stale cross-references, and preserve earlier manuscript files.
