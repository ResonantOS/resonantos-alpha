# Atomic Rebuild Rules
# ResonantOS Logician

reb_operation(/diagram_artboard_rebuild).
reb_operation(/config_file_rewrite).
reb_operation(/template_replacement).
reb_operation(/database_migration).
reb_operation(/file_structure_reorganization).

reb_sequence_step(/create_before_delete, /create_new).
reb_sequence_step(/create_before_delete, /verify_new).
reb_sequence_step(/create_before_delete, /delete_old).

reb_content_has_value(Content) :- reb_is_user_facing(Content).
reb_content_has_value(Content) :- reb_is_shared_document(Content).
reb_content_has_value(Content) :- reb_is_production_config(Content).
reb_content_has_value(Content) :- reb_is_architecture_diagram(Content).

reb_exempt_content(Content) :- reb_is_temp_file(Content).
reb_exempt_content(Content) :- reb_is_cache(Content).
reb_exempt_content(Content) :- reb_is_log_file(Content).

reb_creation_verified(Operation) :- reb_created_replacement(Operation), reb_verified_replacement(Operation).

reb_violation(Agent, /delete_before_create) :-
  reb_initiated_rebuild(Agent, Operation),
  reb_deleted_original(Agent, Operation),
  !reb_creation_verified(Operation).

reb_violation(Agent, /delete_without_replacement) :-
  reb_deleted_content(Agent, Content),
  reb_content_has_value(Content),
  !reb_planned_replacement(Agent, Content).

reb_violation(Agent, /non_atomic_rebuild) :-
  reb_initiated_rebuild(Agent, Operation),
  reb_out_of_order(Operation).

reb_enforcement_stage(/atomic_rebuild, /advisory).
reb_enforcement_stage_override(/atomic_rebuild, /soft_block) :- reb_user_visible_change(/yes).
