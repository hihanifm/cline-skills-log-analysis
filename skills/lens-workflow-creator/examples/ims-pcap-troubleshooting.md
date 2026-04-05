---
workflow: ims-pcap-troubleshooting
skill: lens-workflow-orchestrator-agent
description: IMS/VoLTE network capture analysis — SIP signaling and DNS for call and registration issues


default_max_lines: 200

input:
  - path: "*.pcap*"
    skill: lens-pcap-filter
    include:
      - pcap/sip.yaml
      - pcap/dns.yaml
    templates:
      - id: ims_registration_flow
        filter: "sip.Method == \"REGISTER\" or (sip.Status-Code and sip.CSeq contains \"REGISTER\")"
        fields:
          - frame.number
          - frame.time_relative
          - ip.src
          - ip.dst
          - sip.Method
          - sip.Status-Code
          - sip.Status-Phrase
          - sip.contact_addr
          - sip.Authorization
        description: >
          IMS SIP REGISTER messages and responses. Tracks full registration
          flow: initial REGISTER → 401 Unauthorized (auth challenge) →
          authenticated REGISTER → 200 OK (success) or failure response.
        post_process: decode_sip.py
        summary_prompt: >
          Trace the IMS registration flow. Did registration succeed (200 OK)?
          Was there an authentication challenge (401)? If registration failed,
          what was the error code and what does it indicate?

      - id: volte_call_flow
        filter: "sip.Method == \"INVITE\" or sip.Method == \"BYE\" or sip.Method == \"ACK\" or sip.Method == \"CANCEL\" or (sip.Status-Code and sip.CSeq contains \"INVITE\")"
        fields:
          - frame.number
          - frame.time_relative
          - ip.src
          - ip.dst
          - sip.Method
          - sip.r-uri
          - sip.Status-Code
          - sip.Status-Phrase
          - sip.CSeq
          - sip.Call-ID
        description: >
          VoLTE call signaling flow. Captures INVITE (call setup), ACK,
          BYE (teardown), CANCEL and all intermediate responses.
          Essential for diagnosing call setup failures.
        post_process: decode_sip.py
        summary_prompt: >
          Reconstruct the VoLTE call flow. Did the call connect (183/200 OK
          to INVITE)? If it failed, at which step and with what error?
          Note any call IDs and the complete sequence of events.

final_summary_prompt: >
  Based on all SIP and DNS findings, provide an IMS/VoLTE troubleshooting report:
  (1) Did IMS registration succeed? If not, why?
  (2) Did any VoLTE call attempt succeed? Trace the complete call flow.
  (3) Were there any DNS failures affecting IMS connectivity?
  (4) Root cause hypothesis and recommended next steps.
---

# IMS PCAP Troubleshooting

Run using the `lens-workflow-orchestrator-agent` skill.
