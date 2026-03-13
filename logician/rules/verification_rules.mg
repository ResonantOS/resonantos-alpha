# Verification Before Claim Rules
# ResonantOS Logician

ver_verifiable_claim(/agent_count).
ver_verifiable_claim(/skill_count).
ver_verifiable_claim(/session_count).
ver_verifiable_claim(/cron_job_count).
ver_verifiable_claim(/memory_file_count).
ver_verifiable_claim(/route_count).
ver_verifiable_claim(/plugin_list).
ver_verifiable_claim(/agent_model_assignment).
ver_verifiable_claim(/service_status).
ver_verifiable_claim(/version_number).
ver_verifiable_claim(/sqlite_store_count).
ver_verifiable_claim(/document_count).

ver_verification_method(/agent_count, /openclaw_status).
ver_verification_method(/skill_count, /openclaw_skills_list).
ver_verification_method(/session_count, /openclaw_status).
ver_verification_method(/cron_job_count, /openclaw_cron_list).
ver_verification_method(/memory_file_count, /openclaw_memory_status).
ver_verification_method(/route_count, /grep_route_count).
ver_verification_method(/plugin_list, /openclaw_plugins_list).
ver_verification_method(/agent_model_assignment, /openclaw_agents_list).
ver_verification_method(/service_status, /process_status_check).
ver_verification_method(/version_number, /version_file_or_flag).
ver_verification_method(/sqlite_store_count, /sqlite_file_count).
ver_verification_method(/document_count, /ssot_markdown_count).

ver_valid_claim_label(/verified).
ver_valid_claim_label(/code_reviewed).
ver_valid_claim_label(/untested).
ver_valid_claim_label(/approximate).

ver_violation(Agent, /unverified_fix_claim) :- ver_claimed_fixed(Agent, Component), !ver_verified_by_test(Agent, Component).

ver_violation(Agent, /unverified_state_claim) :-
  ver_asserted_system_state(Agent, ClaimType, Value),
  ver_verifiable_claim(ClaimType),
  !ver_verified_against_source(Agent, ClaimType).

ver_violation(Agent, /stale_verification) :-
  ver_verified_against_source(Agent, ClaimType),
  ver_verification_age_minutes(Agent, ClaimType, AgeMinutes),
  AgeMinutes > 60.

ver_violation(Agent, /unlabeled_claim) :-
  ver_asserted_system_state(Agent, ClaimType, Value),
  ver_verifiable_claim(ClaimType),
  !ver_has_claim_label(Agent, ClaimType, _).

ver_ui_surface(/dashboard_page).
ver_ui_surface(/web_interface).
ver_ui_surface(/telegram_message).
ver_ui_surface(/paper_diagram).

ver_violation(Agent, /no_human_side_verification) :-
  ver_claimed_visible_in_ui(Agent, Component, Surface),
  ver_ui_surface(Surface),
  ver_verified_via_api(Agent, Component),
  !ver_verified_via_ui(Agent, Component, Surface).

ver_human_verification_method(/dashboard_page, /browser_open_screenshot_confirm).
ver_human_verification_method(/web_interface, /browser_navigate_snapshot_check).
ver_human_verification_method(/telegram_message, /delivery_and_readability_confirm).
ver_human_verification_method(/paper_diagram, /screenshot_and_render_confirm).

ver_requires_dual_verification(Action) :- ver_action_adds_to_ui(Action).
ver_requires_dual_verification(Action) :- ver_action_modifies_ui(Action).
ver_requires_dual_verification(Action) :- ver_action_claims_ui_state(Action).

ver_requires_count_verification(/architecture_diagram).
ver_requires_count_verification(/ssot_doc).
ver_requires_count_verification(/status_report).

ver_violation(Agent, /diagram_unverified_data) :-
  ver_updating_document(Agent, DocType),
  ver_requires_count_verification(DocType),
  ver_contains_system_counts(Agent, DocType),
  !ver_all_counts_verified(Agent, DocType).

ver_correct_sequence(/check_system, /write_document).
ver_violation(Agent, /write_before_check) :- ver_action_sequence(Agent, /write_document, /check_system).

ver_enforcement_stage(/verification_before_claim, /advisory).
