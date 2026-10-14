# Sample data

Everything in this folder is fictional: companies, people, projects, issuers and figures. It is safe to use with the free Gemini tier.

## Company packs

Upload these files during company onboarding (Settings, or the "Finish setting up" link in the sidebar).

- **Meridian Integration Labs**: integration and healthcare interoperability specialist (list-style skills matrix, day rates in USD).
- **Cobalt Ridge Technologies**: cloud, data and digital-banking company (rating-grid skills matrix, hourly rates).

## Sample RFP

`sample-rfps/harborline-integration-platform-rfp.docx` is a fictional transit authority's RFP for an integration platform
and a three-year managed service: 85 requirements across functional, real-time, data, non-functional, security,
managed service, delivery, commercial, evaluation and submission sections. It suits the Meridian pack.

To regenerate it: `python -m app.seed.generate_sample_rfp` from the backend folder.
