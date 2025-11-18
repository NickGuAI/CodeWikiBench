## Instructions

**ALWAYS FOLLOW YOUR GUIDING PRINCIPLES - `SIMPLE`**.

### Guiding Principles - SIMPLE

- S: Simplicity is preferred at all times.
  - Short docs
  - Short comments
  - Simple solutions
  - Simple but crucial logs.
- I: Investigate and research solutions before implement.
- M: Maintainability is not an after thought.
  - Code must be easy to read
  - Directory structure must be simple and clear
- P: Purpose Driven Development
  - Start with the purpose of the request
  - Develop corresponding test
  - Write and iterate on code until test passes without changing test code.
- E: Explain your decisions, always.
  - Explain the rootcause before suggesting solutions.
  - Explain the solution before implementation.

### Take Notes

During your interaction with the user, if you find anything reusable across projects (apps/services) (e.g. version of a library, model name), especially about a fix to a mistake you made or a correction you received, you should take note in the 'CLAUDE learned' of the `Lessons` section in the `CLAUDE.md` file so you will not make the same mistake again. 

### Consult Your Peers

1. When starting a project, ask project-manager for the project information.
2. If you are stuck, stop and ask for tech lead input (human).

### Stop and Check
**Stop and validate** at these moments:
- After implementing a complete feature
- Before starting a new major component  
- When something feels wrong
- Before declaring "done"
- **WHEN HOOKS FAIL WITH ERRORS** ❌

Run: `make fmt && make test && make lint`

> Why: You can lose track of what's actually working. These checkpoints prevent cascading failures.

# Lessons

## CLAUDE Learned

### Path Resolution in Python
- When resolving paths relative to current file, use `Path(__file__).resolve().parent` pattern
- For sibling directories: `current_file.parent.parent / "config"` is cleaner than complex join operations
- Always use Path.resolve() to get absolute paths before navigation

### Streamlit UI Best Practices
- Empty checkbox labels cause accessibility warnings
- Use `label_visibility="collapsed"` to hide labels while maintaining accessibility
- Session state should be initialized early with default values
- Auto-loading data on first run improves user experience

### Claude Code SDK Permission Modes
- Permission modes are: `default`, `acceptEdits`, `bypassPermissions` (plan is not supported)
- Permission mode overrides HIL hooks when specified
- Reference SDK documentation for exact parameter values
- **CRITICAL**: `allowed_tools` must be an explicit list of tool names, NOT `["*"]`
- **SIMPLE FIX**: Omit `allowed_tools` parameter when MCPs are enabled to allow all available tools
- MCP tools follow pattern: `mcp__{server}__{tool_name}` (e.g., `mcp__Notion__notion-search`)

### SIMPLE Principle Violations to Avoid
- **Don't hardcode dynamic lists** - MCP tools should be discovered at runtime, not hardcoded
- **Investigate before implementing** - Test assumptions about SDK behavior first
- **Ask clarifying questions** - When user reports "X keeps happening", understand root cause before fixing
- **Maintain simplicity** - If solution requires 60+ hardcoded strings, it's probably wrong
- **Purpose first** - Address the specific need (MCP permissions) not general solutions (all permissions)

### MCP (Model Context Protocol) Configuration
- MCP configs stored as YAML files with transport details
- Each MCP should have descriptive name matching its purpose (e.g., gmail_mcp not relay)
- Tool patterns define which tools the MCP handles (e.g., `find.*` for search operations)
- MCPs can be dynamically enabled/disabled via config

### Database Tracing Implementation
- Store execution traces with: task_id, event_type, event_data, session_id, sequence_num
- Sequence numbers ensure correct event ordering
- JSON serialize event data for flexibility
- Separate traces table allows detailed debugging without cluttering main task records

### API Design Patterns
- Stream progress using SSE (Server-Sent Events) for long-running tasks
- Return task IDs immediately, stream progress separately
- Allow optional parameters to override default behaviors
- Provide both high-level (task) and detailed (trace) views of execution
