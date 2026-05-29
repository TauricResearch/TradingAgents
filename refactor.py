import re

with open('cli/main.py', 'r') as f:
    content = f.read()

# We need to replace `run_analysis` to handle multiple tickers.
# I'll manually replace the entire `run_analysis` function.

run_analysis_code = """
def run_analysis(checkpoint: bool = False):
    # First get all user selections
    selections = get_user_selections()

    # Create config with selected research depth
    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = selections["research_depth"]
    config["max_risk_discuss_rounds"] = selections["research_depth"]
    config["quick_think_llm"] = selections["shallow_thinker"]
    config["deep_think_llm"] = selections["deep_thinker"]
    config["backend_url"] = selections["backend_url"]
    config["llm_provider"] = selections["llm_provider"].lower()
    config["google_thinking_level"] = selections.get("google_thinking_level")
    config["openai_reasoning_effort"] = selections.get("openai_reasoning_effort")
    config["anthropic_effort"] = selections.get("anthropic_effort")
    config["output_language"] = selections.get("output_language", "English")
    config["checkpoint_enabled"] = checkpoint

    selected_set = {analyst.value for analyst in selections["analysts"]}
    selected_analyst_keys = [a for a in ANALYST_ORDER if a in selected_set]
    
    all_ticker_reports = {}

    for current_ticker in selections["ticker"]:
        console.print(f"\\n[bold cyan]Starting analysis for {current_ticker}...[/bold cyan]\\n")
        
        stats_handler = StatsCallbackHandler()
        graph = TradingAgentsGraph(
            selected_analyst_keys,
            config=config,
            debug=True,
            callbacks=[stats_handler],
        )

        message_buffer.init_for_analysis(selected_analyst_keys)
        start_time = time.time()

        results_dir = Path(config["results_dir"]) / current_ticker / selections["analysis_date"]
        results_dir.mkdir(parents=True, exist_ok=True)
        report_dir = results_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        log_file = results_dir / "message_tool.log"
        log_file.touch(exist_ok=True)

        def save_message_decorator(obj, func_name):
            func = getattr(obj, func_name)
            from functools import wraps
            @wraps(func)
            def wrapper(*args, **kwargs):
                func(*args, **kwargs)
                timestamp, message_type, content = obj.messages[-1]
                content = content.replace("\\n", " ")
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"{timestamp} [{message_type}] {content}\\n")
            return wrapper
        
        def save_tool_call_decorator(obj, func_name):
            func = getattr(obj, func_name)
            from functools import wraps
            @wraps(func)
            def wrapper(*args, **kwargs):
                func(*args, **kwargs)
                timestamp, tool_name, args = obj.tool_calls[-1]
                args_str = ", ".join(f"{k}={v}" for k, v in args.items())
                with open(log_file, "a", encoding="utf-8") as f:
                    f.write(f"{timestamp} [Tool Call] {tool_name}({args_str})\\n")
            return wrapper

        def save_report_section_decorator(obj, func_name):
            func = getattr(obj, func_name)
            from functools import wraps
            @wraps(func)
            def wrapper(section_name, content):
                func(section_name, content)
                if section_name in obj.report_sections and obj.report_sections[section_name] is not None:
                    c = obj.report_sections[section_name]
                    if c:
                        file_name = f"{section_name}.md"
                        text = "\\n".join(str(item) for item in c) if isinstance(c, list) else c
                        with open(report_dir / file_name, "w", encoding="utf-8") as f:
                            f.write(text)
            return wrapper

        message_buffer.add_message = save_message_decorator(message_buffer, "add_message")
        message_buffer.add_tool_call = save_tool_call_decorator(message_buffer, "add_tool_call")
        message_buffer.update_report_section = save_report_section_decorator(message_buffer, "update_report_section")

        layout = create_layout()

        with Live(layout, refresh_per_second=4) as live:
            update_display(layout, stats_handler=stats_handler, start_time=start_time)
            message_buffer.add_message("System", f"Selected ticker: {current_ticker}")
            message_buffer.add_message("System", f"Analysis date: {selections['analysis_date']}")
            message_buffer.add_message("System", f"Selected analysts: {', '.join(analyst.value for analyst in selections['analysts'])}")
            update_display(layout, stats_handler=stats_handler, start_time=start_time)

            first_analyst = f"{selections['analysts'][0].value.capitalize()} Analyst"
            message_buffer.update_agent_status(first_analyst, "in_progress")
            update_display(layout, stats_handler=stats_handler, start_time=start_time)

            spinner_text = f"Analyzing {current_ticker} on {selections['analysis_date']}..."
            update_display(layout, spinner_text, stats_handler=stats_handler, start_time=start_time)

            init_agent_state = graph.propagator.create_initial_state(current_ticker, selections["analysis_date"])
            args = graph.propagator.get_graph_args(callbacks=[stats_handler])

            trace = []
            for chunk in graph.graph.stream(init_agent_state, **args):
                for message in chunk.get("messages", []):
                    msg_id = getattr(message, "id", None)
                    if msg_id is not None:
                        if msg_id in message_buffer._processed_message_ids:
                            continue
                        message_buffer._processed_message_ids.add(msg_id)

                    msg_type, content = classify_message_type(message)
                    if content and content.strip():
                        message_buffer.add_message(msg_type, content)

                    if hasattr(message, "tool_calls") and message.tool_calls:
                        for tool_call in message.tool_calls:
                            if isinstance(tool_call, dict):
                                message_buffer.add_tool_call(tool_call["name"], tool_call["args"])
                            else:
                                message_buffer.add_tool_call(tool_call.name, tool_call.args)

                update_analyst_statuses(message_buffer, chunk)

                if chunk.get("investment_debate_state"):
                    debate_state = chunk["investment_debate_state"]
                    bull_hist = debate_state.get("bull_history", "").strip()
                    bear_hist = debate_state.get("bear_history", "").strip()
                    judge = debate_state.get("judge_decision", "").strip()

                    if bull_hist or bear_hist:
                        update_research_team_status("in_progress")
                    if bull_hist:
                        message_buffer.update_report_section("investment_plan", f"### Bull Researcher Analysis\\n{bull_hist}")
                    if bear_hist:
                        message_buffer.update_report_section("investment_plan", f"### Bear Researcher Analysis\\n{bear_hist}")
                    if judge:
                        message_buffer.update_report_section("investment_plan", f"### Research Manager Decision\\n{judge}")
                        update_research_team_status("completed")
                        message_buffer.update_agent_status("Trader", "in_progress")

                if chunk.get("trader_investment_plan"):
                    message_buffer.update_report_section("trader_investment_plan", chunk["trader_investment_plan"])
                    if message_buffer.agent_status.get("Trader") != "completed":
                        message_buffer.update_agent_status("Trader", "completed")
                        message_buffer.update_agent_status("Aggressive Analyst", "in_progress")

                if chunk.get("risk_debate_state"):
                    risk_state = chunk["risk_debate_state"]
                    agg_hist = risk_state.get("aggressive_history", "").strip()
                    con_hist = risk_state.get("conservative_history", "").strip()
                    neu_hist = risk_state.get("neutral_history", "").strip()
                    judge = risk_state.get("judge_decision", "").strip()

                    if agg_hist:
                        if message_buffer.agent_status.get("Aggressive Analyst") != "completed":
                            message_buffer.update_agent_status("Aggressive Analyst", "in_progress")
                        message_buffer.update_report_section("final_trade_decision", f"### Aggressive Analyst Analysis\\n{agg_hist}")
                    if con_hist:
                        if message_buffer.agent_status.get("Conservative Analyst") != "completed":
                            message_buffer.update_agent_status("Conservative Analyst", "in_progress")
                        message_buffer.update_report_section("final_trade_decision", f"### Conservative Analyst Analysis\\n{con_hist}")
                    if neu_hist:
                        if message_buffer.agent_status.get("Neutral Analyst") != "completed":
                            message_buffer.update_agent_status("Neutral Analyst", "in_progress")
                        message_buffer.update_report_section("final_trade_decision", f"### Neutral Analyst Analysis\\n{neu_hist}")
                    if judge:
                        if message_buffer.agent_status.get("Portfolio Manager") != "completed":
                            message_buffer.update_agent_status("Portfolio Manager", "in_progress")
                            message_buffer.update_report_section("final_trade_decision", f"### Portfolio Manager Decision\\n{judge}")
                            message_buffer.update_agent_status("Aggressive Analyst", "completed")
                            message_buffer.update_agent_status("Conservative Analyst", "completed")
                            message_buffer.update_agent_status("Neutral Analyst", "completed")
                            message_buffer.update_agent_status("Portfolio Manager", "completed")

                update_display(layout, stats_handler=stats_handler, start_time=start_time)
                trace.append(chunk)

            final_state = trace[-1]
            decision = graph.process_signal(final_state["final_trade_decision"])

            for agent in message_buffer.agent_status:
                message_buffer.update_agent_status(agent, "completed")

            message_buffer.add_message("System", f"Completed analysis for {selections['analysis_date']}")

            for section in message_buffer.report_sections.keys():
                if section in final_state:
                    message_buffer.update_report_section(section, final_state[section])

            update_display(layout, stats_handler=stats_handler, start_time=start_time)

        console.print(f"\\n[bold cyan]Analysis Complete for {current_ticker}![/bold cyan]\\n")
        
        # Save to all_ticker_reports for super portfolio manager
        all_ticker_reports[current_ticker] = {
            "trader_plan": final_state.get("trader_investment_plan", ""),
            "portfolio_decision": final_state.get("risk_debate_state", {}).get("judge_decision", "")
        }

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_path = Path.cwd() / "reports" / f"{current_ticker}_{timestamp}"
        try:
            report_file = save_report_to_disk(final_state, current_ticker, default_path)
            console.print(f"\\n[green]✓ Report saved to:[/green] {default_path.resolve()}")
        except Exception as e:
            console.print(f"[red]Error saving report: {e}[/red]")

    # Loop is done. Now run Super Portfolio Manager if there's more than one ticker
    if len(selections["ticker"]) > 1:
        console.print("\\n[bold magenta]Running Super Portfolio Manager across all assets...[/bold magenta]\\n")
        from tradingagents.agents.managers.super_portfolio_manager import create_super_portfolio_manager
        from tradingagents.llm_clients import create_llm_client
        
        super_llm = create_llm_client(
            provider=config["llm_provider"],
            model_name=config["deep_think_llm"],
            base_url=config["backend_url"],
            reasoning_effort=config["openai_reasoning_effort"],
            thinking_level=config["google_thinking_level"]
        )
        
        spm_node = create_super_portfolio_manager(super_llm)
        with console.status("[magenta]Super Portfolio Manager is deciding allocation...[/magenta]"):
            spm_result = spm_node({"ticker_reports": all_ticker_reports})
        
        console.print(Panel(Markdown(spm_result["super_portfolio_report"]), title="Super Portfolio Manager Final Allocation", border_style="magenta", padding=(1, 2)))
        
        # Save SPM report
        spm_path = Path.cwd() / "reports" / f"portfolio_allocation_{timestamp}.md"
        with open(spm_path, "w", encoding="utf-8") as f:
            f.write(f"# Super Portfolio Manager Final Allocation\\n\\n{spm_result['super_portfolio_report']}")
        console.print(f"\\n[green]✓ Portfolio allocation saved to:[/green] {spm_path.resolve()}")
"""

# Replace the run_analysis function entirely
# Find where it starts and ends
start_idx = content.find("def run_analysis(checkpoint: bool = False):")
end_idx = content.find("@app.command()")

if start_idx != -1 and end_idx != -1:
    new_content = content[:start_idx] + run_analysis_code + "\n\n" + content[end_idx:]
    with open('cli/main.py', 'w') as f:
        f.write(new_content)
    print("Successfully replaced run_analysis")
else:
    print("Failed to find boundaries")
