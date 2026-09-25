# V2 Engineering Audit and Changelog

## Release intent
V2 is a self-contained, synthetic brownfield repository designed for local engineering analysis and modernization. Intentional legacy contradictions remain because they are part of the system-under-study; accidental defects that prevent installation, import, execution, inspection or reproducibility are release blockers.

## V2 remediation
- Removed restricted answer-key material and all related textual references from the distributable tree.
- Removed cache files, bytecode and internal build-workflow artifacts.
- Normalized project/API version metadata to 2.0.0.
- Added a reproducible repository verifier covering Python syntax, JSON parsing, CSV structural validity, SQLite integrity and release-file presence.
- Added Dockerfile, Makefile and `.env.example` for consistent local deployment.
- Preserved expected-failure tests and deliberately inconsistent synthetic records that represent authentic brownfield conditions.
- Preserved safety boundaries: synthetic/local integrations only; no real-world control or consequential autonomous action surface is configured.
- Added SHA-256 release manifest and recorded verification evidence.

## Interpretation rule
A failed baseline test is a product defect unless it is explicitly marked as an expected legacy limitation with a stated engineering rationale. Data inconsistencies should not be silently 'cleaned' when they are intentional evidence for identity, temporal, semantic, integration, safety, resilience or authority analysis.
