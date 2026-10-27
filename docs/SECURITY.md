# Security

**Controls in place**

- Resume and job text is untrusted. It is wrapped in randomised boundary markers in LLM prompts, with a policy that it
  must not be followed. Instruction-like text is detected at ingestion and the candidate is routed to review.
- Model output is validated with Pydantic. Ratings outside the range and claims without quotes become `needs_review`.
  Every quote is then verified against the same resume.
- No tools are passed to the model.
- Uploads are checked by content (magic bytes), size and structure. Encrypted PDFs and malformed DOCX are rejected,
  files are stored under random names and are never served publicly.
- Authentication uses PBKDF2-SHA256 passwords (390,000 iterations) and HS256 JWTs with revocation on logout. Permissions
  are checked on the server, and every query is filtered by workspace. Login and API rate limits apply. Responses set
  defensive headers and do not include stack traces. Sensitive actions are written to the audit log.

**Test suite v1** (Security and Robustness page) covers eight injection payloads against real resumes, untrusted-block
integrity, eight malformed files, six malformed model outputs, cross-candidate citation leakage, cross-workspace access and
role permissions. It reports measured attempts and successes; it does not claim a defence rate beyond the tests run.

**Known gaps:** the rate limiter and task runner are in-process (use Redis and a worker queue for multiple instances); the
JWT is kept in `sessionStorage` (an httpOnly cookie with CSRF protection is stronger); the suite does not call a live LLM
(run experiment J with the LLM evaluator for that).
