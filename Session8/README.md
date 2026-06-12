# Session 8 - Growing Graph Orchestrator

A production-ready agent system built on a **NetworkX DAG orchestrator** where skills are graph nodes and execution flows through dynamic graph construction. Features parallel execution, critic auto-insertion, failure recovery, and persistent session state.

## DEMO

[Demo Video](https://www.youtube.com/watch?v=Wd-R4BzcQls)

## Queries with Terminal Logs

### Query A. Shannon Wikipedia (S7 carryover)

```
Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth
date, death date, and three key contributions to information theory.
```
```
node 1 / 5
  agent      planner
  status     complete
  elapsed    4.5s
  provider   gemini
  retries    0
  inputs     USER_QUERY
  output     {"rationale": "Fetch the content from the provided URL, then extract the required biographical and professional information.", "nodes": [{"skill": "researcher", "inputs": ["USER_QUERY"], "metadata": {"label": "fetch_shannon", "question": "Fetch the content of https://en.wikipedia.org/wiki/Claude_Shannon"}}, {"skill": "distiller", "inputs": ["n:fetch_shannon"], "metadata": {"label": "extract_info", "question": "Extract birth date, death date, and three key contributions to information theory."}},…> 

node 2 / 5
  agent      researcher
  status     complete
  elapsed    26.7s
  provider   gemini
  retries    0
  inputs     USER_QUERY
  output     {"question": "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birthdate, death date, and three key contributions to information theory.", "sources": [{"url": "https://en.wikipedia.org/wiki/Claude_Shannon", "title": "Claude Shannon - Wikipedia"}, {"url": "https://ethw.org/Claude_Shannon", "title": "Claude Shannon - Engineering and Technology History Wiki"}, {"url": "https://www.lindahall.org/about/news/scientist-of-the-day/claude-shannon", "title": "Claude Shannon - Linda Hall …


node 3 / 5
  agent      distiller
  status     complete
  elapsed    3.6s
  provider   gemini
  retries    0
  inputs     n:2
  output     {"fields": {"birth_date": "April 30, 1916", "death_date": "February 24, 2001", "contributions": ["Identified the 'bit' as the fundamental unit of information", "Developed the concept of channel capacity", "Proved Boolean algebra could be used to design digital switching circuits"]}, "rationale": "All fields were extracted directly from the findings provided in the researcher node output."}> 

node 4 / 5
  agent      formatter
  status     complete
  elapsed    3.6s
  provider   gemini
  retries    0
  inputs     USER_QUERY, n:3
  output     {"final_answer": "Claude Shannon was born on April 30, 1916, and passed away on February 24, 2001. His three key contributions to information theory include: 1) Identifying the 'bit' as the fundamental unit of information; 2) Developing the concept of channel capacity; and 3) Proving that Boolean algebra could be used to design digital switching circuits."}

node 5 / 5
  agent      critic
  status     complete
  elapsed    2.9s
  provider   groq
  retries    0
  inputs     USER_QUERY, n:3
  output     {"verdict": "pass", "rationale": "The output contains the requested birthdate, death date, and three key contributions to information theory, all of which are supported by the input."}

```

### Query I. Three city populations (the parallel-fan-out case)

```
Find the populations of London, Paris, Berlin and tell me which two are
closest in size.
```
```
node 1 / 5
  agent      planner
  status     complete
  elapsed    4.1s
  provider   gemini
  retries    0
  inputs     USER_QUERY
  output     {"rationale": "Fetch the current population for each city in parallel, then use the formatter to perform the comparison.", "nodes": [{"skill": "researcher", "inputs": [], "metadata": {"label": "pop_london", "question": "What is the current population of London?"}}, {"skill": "researcher", "inputs": [], "metadata": {"label": "pop_paris", "question": "What is the current population of Paris?"}}, {"skill": "researcher", "inputs": [], "metadata": {"label": "pop_berlin", "question": "What is the curr…

node 2 / 5
  agent      researcher
  status     complete
  elapsed    22.7s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "What is the current population of London?", "sources": [{"url": "https://trustforlondon.org.uk/data/topics/population", "title": "London's population - Trust For London"}, {"url": "https://trustforlondon.org.uk/data/geography-population", "title": "Demography, London's Population & Geography - Trust For London"}, {"url": "https://www.macrotrends.net/global-metrics/cities/22860/london/population", "title": "London, UK Metro Area Population (1950-2026) | MacroTrends"}], "findings": "…

node 3 / 5
  agent      researcher
  status     complete
  elapsed    31.6s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "What is the current population of Paris?", "sources": [{"url": "https://en.wikipedia.org/wiki/Demographics_of_Paris", "title": "Demographics of Paris - Wikipedia"}, {"url": "https://www.statista.com/statistics/542125/number-of-inhabitants-by-gender-paris-france", "title": "France: population of Paris by gender 2026| Statista"}, {"url": "https://www.macrotrends.net/global-metrics/cities/20985/paris/population", "title": "Paris, France Metro Area Population (1950-2026) | MacroTrends"…

node 4 / 5
  agent      researcher
  status     complete
  elapsed    35.6s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "What is the current population of Berlin?", "sources": [{"url": "https://www.macrotrends.net/global-metrics/cities/204296/berlin/population", "title": "Berlin, Germany Metro Area Population (1950-2026) - Macrotrends"}, {"url": "https://en.wikipedia.org/wiki/Berlin", "title": "Berlin - Wikipedia"}], "findings": "The population of Berlin is approximately 3.7 million inhabitants. Estimates for the metropolitan area population vary slightly depending on the source and specific definiti…

node 5 / 5
  agent      formatter
  status     complete
  elapsed    4.0s
  provider   gemini
  retries    0
  inputs     USER_QUERY, n:2, n:3, n:4
  output     {"final_answer": "Based on the provided data, here are the estimated populations for the three cities:\n\n* London: Approximately 9.1 million (city) to 9.9 million (metro area).\n* Paris: Approximately 2.05 million (city) to 11.4 million (metro area).\n* Berlin: Approximately 3.7 million.\n\nWhen comparing the city-proper populations, Berlin (3.7 million) and Paris (2.05 million) are closer in size to each other than either is to London (9.1 million). However, when comparing metropolitan area po…

```

### Query J. Graceful failure

```
Read /nonexistent/path.txt and tell me what's in it.
```
```
node 1 / 2
  agent      planner
  status     complete
  elapsed    4.0s
  provider   gemini
  retries    0
  inputs     USER_QUERY
  output     {"rationale": "The requested file path does not exist, so I must inform the user that the operation cannot be completed.", "nodes": [{"skill": "formatter", "inputs": ["USER_QUERY"], "metadata": {"label": "out"}}]}

node 2 / 2
  agent      formatter
  status     complete
  elapsed    3.7s
  provider   gemini
  retries    0
  inputs     USER_QUERY
  output     {"final_answer": "I am unable to read the file at /nonexistent/path.txt because it does not exist."}

```

### Query K. Resumable execution

```
For Lagos, Cairo, and Kinshasa, find current populations and growth rates
and tell me which is growing fastest.
```
```
node 1 / 5
  agent      planner
  status     complete
  elapsed    4.7s
  provider   gemini
  retries    0
  inputs     USER_QUERY
  output     {"rationale": "Fetch population and growth rate data for each city in parallel, then compare them to identify the fastest-growing city.", "nodes": [{"skill": "researcher", "inputs": [], "metadata": {"label": "rL", "question": "current population and annual growth rate of Lagos"}}, {"skill": "researcher", "inputs": [], "metadata": {"label": "rC", "question": "current population and annual growth rate of Cairo"}}, {"skill": "researcher", "inputs": [], "metadata": {"label": "rK", "question": "curre…

node 2 / 5
  agent      researcher
  status     complete
  elapsed    42.2s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "current population and annual growth rate of Lagos", "sources": [{"url": "https://www.macrotrends.net/global-metrics/cities/22007/lagos/population", "title": "Lagos, Nigeria Metro Area Population (1950-2026) | MacroTrends"}], "findings": "As of 2026, the estimated metropolitan area population of Lagos, Nigeria, is 17,804,000. This reflects a continued upward trend in the city's demographic growth.\n\nThe annual growth rate for Lagos remains robust. In 2026, the growth rate is recor…

node 3 / 5
  agent      researcher
  status     complete
  elapsed    45.4s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "current population and annual growth rate of Cairo", "sources": [{"url": "https://en.wikipedia.org/wiki/Cairo", "title": "Cairo - Wikipedia"}], "findings": "Cairo is one of the most populous urban areas in the world. Recent estimates for the Cairo metropolitan area indicate a population exceeding 22 million people. The city continues to experience significant demographic pressure and urban expansion.\n\nSpecific, universally agreed-upon annual growth rate figures for the city of Ca…

node 4 / 5
  agent      researcher
  status     complete
  elapsed    37.1s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "current population and annual growth rate of Kinshasa", "sources": [{"url": "https://en.wikipedia.org/wiki/Kinshasa", "title": "Kinshasa - Wikipedia"}], "findings": "Kinshasa is one of the world's fastest-growing megacities. Its population is estimated to reach 18.5 million in 2026. The city experiences rapid demographic expansion driven by high rates of natural increase and significant rural-to-urban migration, with an average of approximately 390,000 new migrants arriving annuall…

node 5 / 5
  agent      formatter
  status     complete
  elapsed    4.9s
  provider   gemini
  retries    0
  inputs     USER_QUERY, n:2, n:3, n:4
  output     {"final_answer": "Here is the population and growth information for the requested cities:\n\n1. Lagos: The 2026 metropolitan population is estimated at 17,804,000, with an annual growth rate of 3.78%.\n2. Cairo: The metropolitan population exceeds 22 million. A specific annual growth rate is not explicitly cited, as the city's demographic expansion is influenced by complex factors including the development of new satellite cities.\n3. Kinshasa: The population is estimated to reach 18.5 million i…
```

## Custom Queries and Their Responses

### Custom Query A. Parallel Fan Out

```
Get me the advantages and disadvantages between Flask, Django and FastAPI
```
```
node 1 / 5
  agent      planner
  status     complete
  elapsed    3.9s
  provider   gemini
  retries    0
  inputs     USER_QUERY
  output     {"rationale": "Since the memory hits do not contain information about web frameworks, I will research Flask, Django, and FastAPI in parallel to gather their respective pros and cons before synthesizing the final comparison.", "nodes": [{"skill": "researcher", "inputs": [], "metadata": {"label": "flask_info", "question": "What are the advantages and disadvantages of the Flask web framework?"}}, {"skill": "researcher", "inputs": [], "metadata": {"label": "django_info", "question": "What are the ad…

node 2 / 5
  agent      researcher
  status     complete
  elapsed    20.2s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "What are the advantages and disadvantages of the Flask web framework?", "sources": [{"url": "https://www.stxnext.com/blog/flask-vs-django-comparison", "title": "Flask vs. Django: Which Python Framework Is Better for Your Web Development?"}, {"url": "https://zyneto.com/blog/flask-for-web-development", "title": "Flask for Web Development: Complete Guide, Benefits & Use Cases"}, {"url": "https://dev.to/detimo/python-flask-pros-and-cons-1mlo", "title": "Python Flask: pros and cons - DE…

node 3 / 5
  agent      researcher
  status     complete
  elapsed    26.9s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "What are the advantages and disadvantages of the Django web framework?", "sources": [{"url": "https://boot.dev/blog/backend/django-for-backend", "title": "The Pros and Cons of Django for Backend Development | Boot.dev"}, {"url": "https://testdriven.io/blog/drf-pros-cons", "title": "Django REST Framework: Pros and Cons | TestDriven.io"}, {"url": "https://www.reddit.com/r/django/comments/16mmwtr/what_do_you_think_are_the_disadvantages_of_django", "title": "What do you think are the d…

node 4 / 5
  agent      researcher
  status     complete
  elapsed    44.3s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "What are the advantages and disadvantages of the FastAPI web framework?", "sources": [{"url": "https://aloa.co/blog/fast-api", "title": "Fast API for Web Development: 2025 Detailed Review"}, {"url": "https://www.planeks.net/pros-and-cons-of-fastapi", "title": "FastAPI Pros and Cons for Custom Web Development - PLANEKS"}], "findings": "FastAPI is a modern, high-performance Python web framework built on Starlette and Pydantic. Its primary advantages include exceptional speed, largely…

node 5 / 5
  agent      formatter
  status     complete
  elapsed    4.5s
  provider   gemini
  retries    0
  inputs     USER_QUERY, n:2, n:3, n:4
  output     {"final_answer": "When choosing between Flask, Django, and FastAPI, the decision typically depends on the scale of your project and your specific performance needs. \n\n### Flask\n*   **Advantages:** Lightweight, highly flexible, and simple to learn. It is ideal for small applications, rapid prototyping, and developers who want full control over their tech stack.\n*   **Disadvantages:** Lacks built-in features (like ORMs or authentication), which can lead to maintenance challenges and fragmented…


node   skill              start (rel)  elapsed    finish (rel)
--------------------------------------------------------------------------------
n:1    planner                 0.00 s     3.88 s       3.88 s
n:2    researcher             97.06 s    20.21 s     117.27 s
n:3    researcher             90.37 s    26.90 s     117.27 s
n:4    researcher             73.02 s    44.26 s     117.27 s
n:5    formatter             117.29 s     4.46 s     121.74 s

wall-clock end-to-end:        121.74 s
sum-of-elapsed (serial):      99.71 s
parallel speedup ratio:         0.82x
```

### Custom Query B. Critic verdict

The Critic must produce both a pass and a fail across two runs of the query, and the fail must successfully splice in a Planner recovery that produces a corrected answer.

```
Find the current exchange rate from USD to INR and also INR to USD. Extract both rates into a structured format showing the base  currency and both target currencies
```
```

node 1 / 10
  agent      planner
  status     complete
  elapsed    3.9s
  provider   gemini
  retries    0
  inputs     USER_QUERY
  output     {"rationale": "Fetch the current exchange rates for both directions and then structure the output.", "nodes": [{"skill": "researcher", "inputs": [], "metadata": {"label": "rate1", "question": "What is the current exchange rate from 1 USD to INR?"}}, {"skill": "researcher", "inputs": [], "metadata": {"label": "rate2", "question": "What is the current exchange rate from 1 INR to USD?"}}, {"skill": "distiller", "inputs": ["n:rate1", "n:rate2"], "metadata": {"label": "data", "question": "Extract the…

node 2 / 10
  agent      researcher
  status     complete
  elapsed    13.8s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "What is the current exchange rate from 1 USD to INR?", "sources": [{"url": "https://www.xe.com/en-us/currencyconverter/convert?Amount=1&From=USD&To=INR", "title": "1 USD to INR - US Dollars to Indian Rupees Exchange Rate"}, {"url": "https://wise.com/us/currency-converter/usd-to-inr-rate", "title": "US dollars to Indian rupees Exchange Rate. Convert USD/INR - Wise"}], "findings": "As of mid-June 2026, the mid-market exchange rate for 1 USD to INR is approximately 95.08 to 95.14 INR.…

node 3 / 10
  agent      researcher
  status     complete
  elapsed    16.8s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "What is the current exchange rate from 1 INR to USD?", "sources": [{"url": "https://www.xe.com/en-us/currencyconverter/convert?Amount=1&From=INR&To=USD", "title": "1 INR to USD - Indian Rupees to US Dollars Exchange Rate"}, {"url": "https://wise.com/us/currency-converter/inr-to-usd-rate", "title": "Indian rupees to US dollars Exchange Rate. Convert INR/USD - Wise"}], "findings": "As of the most recent market data, the mid-market exchange rate for 1 Indian Rupee (INR) to US Dollar (…

node 4 / 10
  agent      distiller
  status     complete
  elapsed    3.5s
  provider   gemini
  retries    0
  inputs     n:2, n:3
  output     {"fields": {"USD_to_INR_rate": "95.08 - 95.14 INR", "INR_to_USD_rate": "0.0105 USD", "date": "mid-June 2026"}, "rationale": "The exchange rates and date are extracted from the findings in nodes n:2 and n:3."}

node 5 / 10
  agent      critic
  status     complete
  elapsed    3.0s
  provider   groq
  retries    0
  inputs     USER_QUERY, n:4
  output     {"verdict": "fail", "rationale": "The output is missing a structured format showing the base currency and both target currencies as requested in the user query."}

node 6 / 10
  agent      planner
  status     complete
  elapsed    4.1s
  provider   gemini
  retries    0
  inputs     USER_QUERY
  output     {"rationale": "Fetch the current exchange rates for USD-INR and INR-USD using the researcher, then use the distiller to ensure the output is strictly structured as requested.", "nodes": [{"skill": "researcher", "inputs": [], "metadata": {"label": "fetch_rates", "question": "What is the current exchange rate for 1 USD to INR and 1 INR to USD?"}}, {"skill": "distiller", "inputs": ["n:fetch_rates"], "metadata": {"label": "structure_data", "question": "Extract the exchange rates into a structured fo…

node 7 / 10
  agent      researcher
  status     complete
  elapsed    12.5s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "What is the current exchange rate for 1 USD to INR and 1 INR to USD?", "sources": [{"url": "https://www.xe.com/en-us/currencyconverter/convert?Amount=1&From=USD&To=INR", "title": "1 USD to INR - US Dollars to Indian Rupees Exchange Rate"}, {"url": "https://www.xe.com/en-us/currencyconverter/convert?Amount=1&From=INR&To=USD", "title": "1 INR to USD - Indian Rupees to US Dollars Exchange Rate"}, {"url": "https://wise.com/us/currency-converter/inr-to-usd-rate", "title": "Indian rupees…

node 8 / 10
  agent      distiller
  status     complete
  elapsed    4.0s
  provider   gemini
  retries    0
  inputs     n:8
  output     {"fields": {"USD_to_INR": "95.14", "INR_to_USD": "0.0105"}, "rationale": "The findings from node n:8 explicitly state the mid-market exchange rates for 1 USD to INR and 1 INR to USD."}

node 9 / 10
  agent      critic
  status     complete
  elapsed    3.2s
  provider   groq
  retries    0
  inputs     n:9
  output     {"verdict": "pass", "rationale": "The output contains the required fields for USD to INR and INR to USD exchange rates."}

node 10 / 10
  agent      formatter
  status     complete
  elapsed    3.8s
  provider   gemini
  retries    0
  inputs     USER_QUERY, n:10
  output     {"final_answer": "The current exchange rates are as follows:\n\n| Base Currency | Target Currency | Exchange Rate |\n| :--- | :--- | :--- |\n| USD | INR | 84.07 |\n| INR | USD | 0.0119 |"}

```

**Here, the critic failed the distiller's output, then the graph was rerun again from planner.**

### Custom Query C. Coder Skill demonstartion

```
I have invested Rs 20000 in a mutual fund SIP with 12% CAGR annualy. Calculate my corpus value after 15 years
```
```
node 1 / 4
  agent      planner
  status     complete
  elapsed    4.1s
  provider   gemini
  retries    0
  inputs     USER_QUERY
  output     {"rationale": "The query requires a mathematical calculation for a SIP investment, which is best handled by the coder to ensure accuracy.", "nodes": [{"skill": "coder", "inputs": ["USER_QUERY"], "metadata": {"label": "calc", "question": "Calculate the future value of a monthly SIP of Rs 20,000 for 15 years at an annual interest rate of 12% (compounded monthly)."}}, {"skill": "formatter", "inputs": ["USER_QUERY", "n:calc"], "metadata": {"label": "out"}}]}

node 2 / 4
  agent      coder
  status     complete
  elapsed    4.3s
  provider   gemini
  retries    0
  inputs     USER_QUERY
  output     {"code": "monthly_investment = 20000\nannual_rate = 0.12\nmonthly_rate = annual_rate / 12\nyears = 15\nmonths = years * 12\n\n# Formula for Future Value of SIP: FV = P * [((1 + r)^n - 1) / r] * (1 + r)\n# P = monthly investment, r = monthly rate, n = total months\nfuture_value = monthly_investment * (((1 + monthly_rate)**months - 1) / monthly_rate) * (1 + monthly_rate)\n\nprint(f'Future Value: {future_value:,.2f}')", "rationale": "Calculate the future value of a monthly SIP using the standard fo…

node 3 / 4
  agent      formatter
  status     complete
  elapsed    3.8s
  provider   gemini
  retries    0
  inputs     USER_QUERY, n:2
  output     {"final_answer": "If you invest Rs 20,000 per month in a mutual fund SIP with an annual return of 12% (CAGR) for a period of 15 years, your total corpus value will be Rs 1,01,45,931.25."}

node 4 / 4
  agent      sandbox_executor
  status     complete
  elapsed    0.3s
  provider   —
  retries    0
  inputs     n:2
  output     {"exit_code": 0, "stdout": "Future Value: 10,091,519.99\r\n", "stdout_truncated": false, "stderr": "", "stderr_truncated": false, "files_written": [], "timed_out": false, "cwd": "C:\\Users\\ANUBHA~1.PAN\\AppData\\Local\\Temp\\s8sandbox-924aj_pe"}
```

### Custom Query D. New skill - scenario-modeler demonstration

```
What if there is a copper shortage in the world in the next year. Estimate the price of copper at the end of 2027 and compare it to today's price based on this scenario
```
```
node 1 / 4
  agent      planner
  status     complete
  elapsed    5.0s
  provider   gemini
  retries    0
  inputs     USER_QUERY
  output     {"rationale": "To estimate the impact of a copper shortage on 2027 prices, I need to research current market trends and then use a scenario modeler to simulate the economic effects.", "nodes": [{"skill": "researcher", "inputs": [], "metadata": {"label": "market_data", "question": "What is the current global market price of copper and what are the primary drivers of copper supply and demand for 2025-2027?"}}, {"skill": "scenario_modeler", "inputs": ["n:market_data"], "metadata": {"label": "model"…

node 2 / 4
  agent      researcher
  status     complete
  elapsed    28.9s
  provider   gemini
  retries    0
  inputs     (none)
  output     {"question": "What is the current global market price of copper and what are the primary drivers of copper supply and demand for 2025-2027?", "sources": [{"url": "https://www.goldmansachs.com/insights/articles/copper-prices-forecast-to-decline-from-record-highs-in-2026", "title": "Copper Prices Are Forecast to Decline Somewhat from Record Highs in 2026 | Goldman Sachs"}, {"url": "https://www.jpmorgan.com/insights/global-research/commodities/copper-outlook", "title": "Copper Prices Outlook | J.P.…

node 3 / 4
  agent      scenario_modeler
  status     complete
  elapsed    5.7s
  provider   gemini
  retries    0
  inputs     n:2
  output     {"baseline_scenario": {"name": "Market Moderation", "initial_state": "Copper trading at ~$6.40/lb ($14,100/tonne) with forecasts suggesting a gradual decline toward $10,000-$13,500/tonne by end of 2027 due to supply surpluses.", "key_parameters": {"price_per_lb": 6.4, "market_balance": "surplus", "demand_drivers": "energy transition, AI infrastructure"}}, "alternative_scenarios": [{"name": "Global Copper Shortage", "initial_change": "Acute supply contraction (e.g., major mine closures or geopoli…

node 4 / 4
  agent      formatter
  status     complete
  elapsed    3.8s
  provider   gemini
  retries    0
  inputs     USER_QUERY, n:3
  output     {"final_answer": "In the event of a global copper shortage, the price of copper is estimated to reach approximately $7.75 per pound by the end of 2027. This represents a significant increase compared to today's price of approximately $6.40 per pound. Under this shortage scenario, the market would shift from a surplus to a structural deficit, leading to an initial price spike followed by stabilization as manufacturers increase the use of substitutes like aluminum and secondary production (recycli…
```

## Architecture Overview

Session 8 replaces the linear MPDA loop with a **growing directed acyclic graph (DAG)**. The Planner emits an initial skill graph, which grows at runtime through five mechanisms:

1. **Planner seed plan** - Initial batch of nodes from user query
2. **Dynamic successors** - Skills can emit new nodes via `AgentResult.successors`
3. **Static internal_successors** - YAML-defined automatic successors (e.g., Coder → SandboxExecutor)
4. **Critic auto-insertion** - Orchestrator injects Critic nodes after `critic: true` skills
5. **Recovery re-planning** - Planner invoked on node failure to create recovery subgraph

```
┌─────────────────────────────────────────────────────────────┐
│                     Session 8 Flow                          │
│                                                              │
│  USER_QUERY → Planner → [n:1 researcher, n:2 researcher,   │
│                          n:3 distiller, n:4 formatter]      │
│                                                              │
│  Orchestrator executes DAG:                                 │
│   - n:1, n:2 run in parallel (ready nodes)                 │
│   - n:3 waits for both (predecessors)                      │
│   - Auto-insert n:5 critic between n:3 → n:4              │
│   - n:4 runs after critic passes                           │
│                                                              │
│  Persistence: graph.json, nodes/n_001.json, ...            │
│  Resumption: --resume <session_id> continues pending nodes │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Features

### 1. **Dynamic DAG Execution**
- **Parallel execution**: Ready nodes run concurrently via `asyncio.gather`
- **Topological ordering**: Nodes only execute when all predecessors complete
- **NetworkX backend**: Full graph operations (cycles detection, traversal, subgraph isolation)

### 2. **Skills as Nodes**
11 production skills:
- **planner** - Decomposes queries into DAG nodes
- **researcher** - Multi-step web research (`web_search`, `fetch_url`)
- **retriever** - Vector search over FAISS-indexed knowledge
- **distiller** - Structured field extraction with critic auto-insertion
- **summariser** - Content condensation
- **synthesizer** - Knowledge graph construction from multi-source exploration
- **scenario_modeler** - What-if counterfactual simulation with cascade effects
- **critic** - Pass/fail evaluation with recovery trigger
- **formatter** - Terminal node rendering final answer
- **coder** - Python code emission
- **sandbox_executor** - Isolated code execution

### 3. **Critic Auto-Insertion & Recovery**
- Skills marked `critic: true` in YAML trigger auto-insertion
- Critic gates all outgoing edges (both dynamic and planner-generated)
- Fail verdict → Planner recovery node → alternate path

### 4. **Persistent Sessions**
- **Graph state**: `state/sessions/<sid>/graph.json` (NetworkX serialization)
- **Node states**: `state/sessions/<sid>/nodes/n_001.json` (per-node results)
- **Resume mode**: `--resume <session_id>` continues from pending nodes
- **UTF-8 safe**: All file I/O with explicit encoding

### 5. **Session Statistics**
Automatic parallel execution metrics:
```
node   skill              start (rel)  elapsed    finish (rel)
n:1    planner                0.00 s     2.18 s       2.18 s
n:2    researcher             2.18 s    40.50 s      42.69 s
n:3    researcher             5.80 s    36.89 s      42.69 s
n:4    coder                 42.69 s    18.56 s      61.26 s

wall-clock end-to-end:       61.26 s
sum-of-elapsed (serial):    99.32 s
parallel speedup ratio:       1.62x
```

### 6. **Tracer System**
Comprehensive execution logging:
- Session start with memory hits
- Node lifecycle (start/complete/failed)
- Tool calls with arguments and results
- Successor node emission
- Recovery events
- File output: `logs/session_<sid>_<timestamp>.log`

---

## Quick Start

### Prerequisites
1. **LLM Gateway V8** - Path: `D:\2026\EAG3\resources\llm_gatewayV8`
2. **Python 3.11+**
3. **MCP Server** running on port 8008

### Step 1: Start MCP Server
```bash
cd Session8
python mcp_server.py
```
Server starts on **http://127.0.0.1:8008/mcp**

### Step 2: Run Agent (Single Query)
```bash
cd Session8
python flow.py "Find the current exchange rate from USD to EUR and USD to GBP"
```

### Step 3: Interactive Mode
```bash
cd Session8
python interactive.py
```
Continuous query loop with session logging.

### Step 4: Resume Session
```bash
cd Session8
python flow.py --resume s8-abc12345
# or
python interactive.py --resume s8-abc12345
```

---

## Technology Stack

- **Orchestrator**: NetworkX DAG with asyncio parallel execution
- **Persistence**: JSON (graph state) + Pydantic (node schemas)
- **Skills**: YAML-defined, prompt-based, no Python classes
- **Tools**: MCP HTTP/SSE transport (11 tools: web, files, knowledge)
- **LLM**: Multi-provider via Gateway V8 (Gemini, GPT, Groq, Claude)
- **Memory**: FAISS vector search + keyword fallback
- **Sandbox**: Subprocess Python runner with 30s timeout


---

## File Structure

```
Session8/
├── flow.py                  # Main orchestrator (Executor + Graph)
├── interactive.py           # REPL interface with session logging
├── skills.py                # Skill registry + execution dispatcher
├── schemas.py               # Pydantic models (AgentResult, NodeState)
├── persistence.py           # Session state save/load (graph + nodes)
├── recovery.py              # Failure handling + recovery policy
├── tracer.py                # Execution logging system
├── session_stats.py         # Parallel speedup metrics
├── memory.py                # FAISS-backed vector memory
├── artifacts.py             # Large result blob storage
├── sandbox.py               # Code execution sandbox
├── mcp_server.py            # 11 MCP tools (web, files, knowledge)
├── mcp_runner.py            # Tool-use loop coordinator
├── gateway.py               # LLM Gateway V8 client
├── agent_config.yaml        # Skill catalog (11 skills)
├── prompts/                 # Skill system prompts (.md files)
│   ├── planner.md
│   ├── researcher.md
│   ├── distiller.md
│   ├── synthesizer.md
│   ├── scenario_modeler.md
│   └── ...
├── state/sessions/          # Persistent session data
│   └── s8-abc12345/
│       ├── query.txt
│       ├── graph.json
│       └── nodes/
│           ├── n_001.json
│           ├── n_002.json
│           └── ...
├── logs/                    # Tracer output
└── sandbox/                 # Coder/file tool workspace
```

---

## Advanced Features

### Parallel Fan-Out
Planner can emit N workers for "compare A, B, C" queries.

### Knowledge Graph Synthesis
The `synthesizer` skill builds multi-source knowledge graphs.

### What-If Scenario Modeling
The `scenario_modeler` simulates counterfactuals with cascade effects.

### Critic-Driven Refinement
Distiller outputs auto-trigger Critic verification with recovery on fail.

---

## Differences from Session 7

| Feature | Session 7 (MPDA) | Session 8 (DAG) |
|---------|------------------|-----------------|
| **Architecture** | Linear loop | Dynamic growing DAG |
| **Parallelism** | Sequential | Concurrent ready nodes |
| **Planning** | One-shot goals | Multi-stage graph |
| **Recovery** | Manual retry | Auto Planner recovery |
| **Skills** | Hardcoded | YAML-defined |
| **Persistence** | Memory only | Full graph state |