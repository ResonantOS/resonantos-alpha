# Behavioral Integrity Rules
# ResonantOS Logician

bir_challenge_pattern(/this_is_wrong).
bir_challenge_pattern(/thats_incorrect).
bir_challenge_pattern(/you_made_a_mistake).
bir_challenge_pattern(/this_does_not_work).
bir_challenge_pattern(/are_you_sure).
bir_challenge_pattern(/check_again).
bir_challenge_pattern(/you_forgot).

bir_challenge_type(/factual_correction).
bir_challenge_type(/behavioral_critique).
bir_challenge_type(/state_assertion).
bir_challenge_type(/identity_claim).

bir_required_response_step(1, /acknowledge_challenge).
bir_required_response_step(2, /independent_verification).
bir_required_response_step(3, /report_with_evidence).

bir_violation(Agent, /reflexive_agreement) :-
  bir_received_challenge(Agent, Challenge),
  bir_responded_with_agreement(Agent, Challenge),
  !bir_performed_verification(Agent, Challenge).

bir_violation(Agent, /unsupported_disagreement) :-
  bir_received_challenge(Agent, Challenge),
  bir_responded_with_disagreement(Agent, Challenge),
  !bir_cited_evidence(Agent, Challenge).

bir_violation(Agent, /skipped_acknowledgment) :-
  bir_received_challenge(Agent, Challenge),
  !bir_acknowledged_challenge(Agent, Challenge),
  bir_responded_with_agreement(Agent, Challenge).

bir_violation(Agent, /skipped_acknowledgment) :-
  bir_received_challenge(Agent, Challenge),
  !bir_acknowledged_challenge(Agent, Challenge),
  bir_responded_with_disagreement(Agent, Challenge).

bir_violation(Agent, /sycophantic_reversal) :-
  bir_received_challenge(Agent, Challenge),
  bir_changed_position(Agent, Challenge),
  !bir_new_evidence_provided(Agent, Challenge).

bir_violation(Agent, /uncritical_frame_adoption) :-
  bir_received_challenge(Agent, Challenge),
  bir_adopted_frame(Agent, Challenge),
  !bir_verified_frame(Agent, Challenge).

bir_violation(Agent, /missed_ip_recognition) :-
  bir_referenced_named_concept(Agent, Concept),
  bir_registered_ip(Concept, /owner),
  !bir_recognized_as_ip(Agent, Concept).

bir_requires_ip_check(Concept) :- bir_is_framework(Concept).
bir_requires_ip_check(Concept) :- bir_is_book_title(Concept).
bir_requires_ip_check(Concept) :- bir_is_methodology(Concept).
bir_requires_ip_check(Concept) :- bir_is_branded_term(Concept).

bir_enforcement_stage(/behavioral_integrity, /advisory).
bir_enforcement_stage_override(/behavioral_integrity, /soft_block) :- bir_violation(/any_agent, /sycophantic_reversal).
