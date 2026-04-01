---
workflow: emergency-call-troubleshooting
skill: workflow-orchestrator
description: Emergency call (E911/SOS) failure analysis for Android devices

output:
  # Relative subdirectory under WORKFLOW_OUTPUT_DIR (if set),
  # otherwise relative to the input file location.
  dir: ./emergency-call-analysis-output
  filename: "emergency_call_{{timestamp}}.txt"

default_max_lines: 200

input:
  - path: "logcat*.txt"
    skill: android-log-analysis
    include:
      - log/ims-sip.yaml
      - log/ril.yaml
    templates:
      - id: emergency_call_attempt
        pattern: "EmergencyCall|emergency.*call|EMERGENCY_CALL|dial.*911|dial.*112|dial.*SOS"
        context_lines: 10
        description: >
          Emergency call attempt events. Captures the initiation of E911/SOS
          calls from the telephony framework layer.
        post_process: decode_carriers.py
        summary_prompt: >
          Describe each emergency call attempt found. Did it succeed or fail?
          At what layer did any failure occur (app, IMS, RIL, network)?

      - id: ims_emergency
        pattern: "IMS.*(emergency|E911|SOS|EMERGENCY)"
        context_lines: 10
        description: >
          IMS layer emergency call handling. VoLTE emergency calls go through
          IMS — failures here indicate IMS registration or routing issues.
        post_process: decode_carriers.py
        summary_prompt: >
          Was the IMS layer able to handle the emergency call? Note any
          fallback to CS (circuit-switched) domain.

      - id: call_failed
        pattern: "call.*(fail|error|reject|disconnect|DROP)|CALL_FAIL|DisconnectCause"
        context_lines: 5
        description: >
          Call failure and disconnect cause events. DisconnectCause codes
          indicate why a call ended unexpectedly.
        summary_prompt: >
          List all call failure events with their disconnect cause codes.
          Translate any numeric codes to their meaning (e.g. NORMAL=16,
          EMERGENCY_TEMP_FAILURE=65) and indicate if they suggest a
          network or device issue.

  - path: "bugreport*.txt"
    skill: android-log-analysis
    include:
      - log/ril.yaml
    templates:
      - id: no_service
        pattern: "no.*service|NO_SERVICE|OUT_OF_SERVICE|signal.*lost|NETWORK_TYPE_UNKNOWN"
        context_lines: 5
        description: >
          No service / out of service events. If the device had no network
          coverage at the time of the emergency call, this explains the failure.
        summary_prompt: >
          Was the device out of service at the time of the emergency call?
          Note how long the no-service condition lasted and whether
          limited-service mode was available.

final_summary_prompt: >
  Based on all pattern findings, provide an emergency call troubleshooting report:
  (1) Did the emergency call attempt succeed? If not, at which layer did it fail?
  (2) Was IMS/VoLTE available or did it fall back to CS?
  (3) Was there a coverage issue (no service / poor signal)?
  (4) Root cause hypothesis and recommended fix or escalation path.
---

# Emergency Call Troubleshooting

Run using the `workflow-orchestrator` skill.
