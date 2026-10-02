"""Checkpointed CLI streaming, including the state saved before an interruption."""


def stream_with_checkpoint(graph, initial_state, args, selections):
    if not graph.config.get("checkpoint_enabled"):
        yield from graph.stream_run(initial_state, **args)
        return
    with graph.checkpoint_scope(
        selections["ticker"], selections["analysis_date"], selections["asset_type"]
    ) as thread_id:
        stream_args = dict(args)
        config = dict(stream_args.get("config", {}))
        config["configurable"] = {**config.get("configurable", {}), "thread_id": thread_id}
        stream_args["config"] = config
        yield from graph.stream_run(graph.checkpoint_input(initial_state), **stream_args)
        # Resumed streams emit only new node updates. Include the saved analyst
        # reports so the final report is complete even if only the PM ran now.
        yield [], graph.graph.get_state(config).values
