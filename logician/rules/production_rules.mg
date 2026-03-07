
% ----------------------------------------------------------------------------
% HALT PROTOCOL (Simplified) - Input Quality Check
% Added 2026-03-07
% ----------------------------------------------------------------------------
% Before processing ANY human prompt, ask these 2 questions:
% 1. Is it clear?
% 2. Do I have enough data to proceed?
% 
% If NO to either → ask for clarification
% If YES to both → proceed
%
% Who follows this: orchestrator, voice agent, DAO agent
% Who doesn't: Codex (has DELEGATION_PROTOCOL), Perplexity (has RESEARCH_PROTOCOL)

halt_on_prompt(Agent) :- 
    member(Agent, [orchestrator, voice, dao]).

% Rule: Before processing, check clarity and sufficiency
violation(Agent, skip_halt_check) :-
    halt_on_prompt(Agent),
    received_prompt(Agent, Prompt),
    \+ halt_checked(Prompt, Agent).

% Rule: Must ask if unclear
violation(Agent, proceed_without_clarification) :-
    prompt_unclear(Prompt),
    \+ asked_for_clarification(Prompt, Agent).

% Rule: Must ask if insufficient data
violation(Agent, proceed_without_data) :-
    prompt_insufficient_data(Prompt),
    \+ asked_for_more_info(Prompt, Agent).

% Vague terms that indicate unclear prompt
vague_term("fix").
vague_term("bug").
vague_term("improve").
vague_term("change").
vague_term("update").
vague_term("something").
vague_term("stuff").
vague_term("etc").

prompt_unclear(Prompt) :-
    vague_term(Word),
    sub_string(Prompt, _, _, _, Word),
    \+ has_specifics(Prompt).

% Required context per task type
required_context(coding, [file_path, expected_behavior, error_message]).
required_context(research, [question, scope, timeframe]).
required_context(general, []).

prompt_insufficient_data(Prompt) :-
    required_context(Type, Required),
    member(Context, Required),
    \+ contains(Prompt, Context).

% What to say when asking for clarification
halt_response("Your prompt is unclear. I need more details to proceed.
    
Can you clarify:
1. What exactly do you want?
2. What would success look like?
3. Any constraints or requirements?").

