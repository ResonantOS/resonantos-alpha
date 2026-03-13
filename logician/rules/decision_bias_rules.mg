# Decision Bias Rules
# ResonantOS Logician

db_filter_priority(1, /free_over_paid).
db_filter_priority(2, /safe_over_risky).
db_filter_priority(3, /deterministic_over_ai).
db_filter_priority(4, /oss_over_custom).
db_filter_priority(5, /simple_over_complex).
db_filter_priority(6, /local_over_remote).

db_option_eliminable(Option, Filter) :-
  db_filter_priority(_, Filter),
  db_violates_filter(Option, Filter),
  db_better_alternative_exists(Option, Filter).

db_single_survivor(Option) :-
  db_candidate_option(Option),
  !db_option_eliminable(Option, _),
  db_all_others_eliminable(Option).

db_must_act_not_ask(/yes) :- db_single_survivor(_).

db_unnecessary_options_presented(/yes) :-
  db_options_presented_state(/multiple),
  db_must_act_not_ask(/yes).

db_violates_filter(Option, /safe_over_risky) :- db_option_has_risk(Option).
db_violates_filter(Option, /free_over_paid) :- db_option_has_cost(Option), db_free_alternative_exists(/yes).
db_violates_filter(Option, /deterministic_over_ai) :- db_option_uses_ai(Option), db_deterministic_solution_exists(/yes).

db_contradicts_core_principles(Option) :- db_option_has_risk(Option), db_building_trustworthy_system(/yes).
db_contradicts_core_principles(Option) :- db_option_accepts_known_bug(Option), db_building_reliable_system(/yes).

db_building_trustworthy_system(/yes).
db_building_reliable_system(/yes).

db_not_real_option(Option) :- db_contradicts_core_principles(Option).

db_decision_bias_block(/unnecessary_options) :- db_unnecessary_options_presented(/yes).
db_decision_bias_warn(/explain_tradeoff) :- db_options_presented_state(/multiple), !db_must_act_not_ask(/yes).
