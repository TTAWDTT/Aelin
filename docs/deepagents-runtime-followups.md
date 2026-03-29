# DeepAgents Runtime Follow-ups

## Pending

- [ ] Investigate long-tail completion after successful `device` actions on Windows dev runtime.
  - Symptom:
    - Remote-control style runs can successfully call `device.open_aelin` and open `/settings`, but the overall LangGraph run may keep running for several minutes before finally completing.
    - This does not look like a pure model-quality issue, because the tool action itself succeeds and the backend eventually reports `Background run succeeded`.
  - Confirmed evidence:
    - `POST https://124.220.71.236:8000/v1/chat/completions` returns `200 OK`.
    - `POST http://127.0.0.1:21914/v1/desktop/app/activate` returns `200 OK`.
    - The same run can still remain active for a very long time before the worker reports completion.
  - Runtime warnings seen during the same test window:
    - LangGraph dev repeatedly logs `watchfiles ... changes detected`.
    - Windows checkpoint persistence logs `BlockingError: Blocking call to os.unlink`.
    - Windows checkpoint persistence also logs `FileExistsError` around `.langgraph_api/.langgraph_checkpoint.*`.
  - Current hypothesis:
    - The main blocker is likely in the local LangGraph dev runtime on Windows:
      - watch/reload noise around runtime files,
      - checkpoint persistence behavior,
      - and single-worker queue amplification.
    - This is more likely than “the model cannot decide whether to stop”.
  - Next steps:
    - Check whether `.langgraph_api` or other runtime artifacts are being watched unnecessarily.
    - Move runtime persistence outputs away from watched source paths if possible.
    - Test LangGraph dev with `--allow-blocking` in local Windows development.
    - Test `BG_JOB_ISOLATED_LOOPS=true` for background runs.
    - Re-run remote-control E2E after runtime stabilization and compare completion time.

