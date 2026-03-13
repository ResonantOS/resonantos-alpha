# Research Rules
# ResonantOS Logician

res_research_tool(/brave_api, /quick).
res_research_tool(/perplexity, /standard).
res_research_tool(/perplexity_pro, /deep).

res_tool_tier(/brave_api, 1).
res_tool_tier(/perplexity, 2).
res_tool_tier(/perplexity_pro, 3).

res_can_use(/researcher, /brave_api).
res_can_use(/researcher, /perplexity).
res_can_use(/researcher, /perplexity_pro).

res_can_use(/main, /brave_api).
res_can_use(/dao, /brave_api).
res_can_use(/dao, /perplexity).
res_can_use(/voice, /brave_api).
res_can_use(/website, /brave_api).
res_can_use(/creative, /brave_api).
res_can_use(/blindspot, /brave_api).

res_rate_limit(/main, /brave_api, 50).
res_rate_limit(/doer, /brave_api, 30).
res_rate_limit(/website, /brave_api, 20).
res_rate_limit(/dao, /brave_api, 30).
res_rate_limit(/researcher, /brave_api, 100).
res_rate_limit(/researcher, /perplexity, 30).
res_rate_limit(/dao, /perplexity, 15).
res_rate_limit(/researcher, /perplexity_pro, 10).

res_within_rate_limit(Agent, Tool) :-
  res_rate_limit(Agent, Tool, Max),
  res_current_usage(Agent, Tool, Current),
  Current < Max.

res_block_tool_use(Agent, Tool) :-
  res_rate_limit(Agent, Tool, Max),
  res_current_usage(Agent, Tool, Current),
  Current >= Max.

res_research_depth(Query, /quick) :- res_quick_indicator(Query), !res_standard_indicator(Query), !res_deep_indicator(Query).
res_research_depth(Query, /standard) :- res_standard_indicator(Query), !res_deep_indicator(Query).
res_research_depth(Query, /deep) :- res_deep_indicator(Query).
res_research_depth(Query, /quick) :- !res_quick_indicator(Query), !res_standard_indicator(Query), !res_deep_indicator(Query).

res_must_delegate_research(Agent, Query, /researcher) :- res_research_depth(Query, /standard), !res_can_use(Agent, /perplexity).
res_must_delegate_research(Agent, Query, /researcher) :- res_research_depth(Query, /deep), !res_can_use(Agent, /perplexity_pro).

res_non_researcher_agent(/main).
res_non_researcher_agent(/dao).
res_non_researcher_agent(/doer).
res_non_researcher_agent(/website).
res_non_researcher_agent(/voice).
res_non_researcher_agent(/creative).
res_non_researcher_agent(/setup).
res_non_researcher_agent(/acupuncturist).
res_non_researcher_agent(/blindspot).
res_should_delegate_research(Agent, Query, /researcher) :- res_research_depth(Query, /deep), res_non_researcher_agent(Agent).

res_violation(Agent, /unauthorized_tool_use, Tool) :- res_used_tool(Agent, Tool), !res_can_use(Agent, Tool).
res_violation(Agent, /failed_to_delegate, Query) :- res_must_delegate_research(Agent, Query, /researcher), res_did_research_self(Agent, Query).

res_suggest_upgrade(Query, /perplexity) :- res_research_outcome(Query, /brave_api, /insufficient).
res_suggest_upgrade(Query, /perplexity_pro) :- res_research_outcome(Query, /perplexity, /insufficient).
res_suggest_downgrade(Query, /perplexity) :- res_research_outcome(Query, /perplexity_pro, /excessive).
res_suggest_downgrade(Query, /brave_api) :- res_research_outcome(Query, /perplexity, /excessive).

res_violation(/main, /manual_deep_research, /none) :- res_research_depth(/current_query, /deep), !res_perplexity_used(/current_query).
res_violation(/main, /no_alert_on_perplexity_fail, /none) :- res_perplexity_failed(Error), !res_human_informed(/perplexity_failed, Error).
res_non_deep_mode(/quick).
res_non_deep_mode(/standard).
res_violation(/main, /wrong_search_mode, /none) :- res_research_depth(/current_query, /deep), res_search_mode(/current_query, Mode), res_non_deep_mode(Mode), !res_human_approved(/quick_mode).
