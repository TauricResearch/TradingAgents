# 🚀 Scopecraft  Quick Start Guide

Welcome to Scopecraft ! This guide will help you get started with the new workflow-based task system.

## 📋 Workflow States

Tasks move through three workflow states:

1. **📥 Backlog**: Future work not yet started
2. **🔄 Current**: Active work in progress  
3. **✅ Archive**: Completed work

## 🎯 Basic Commands

### Creating Tasks
```bash
# Create a new task (goes to backlog by default)
sc task create --title "Add user authentication" --type feature --area auth

# Create and start immediately (goes to current)
sc task create --title "Fix login bug" --type bug --area auth --current

# Create from a template
sc task create --template feature --title "New Feature" --area ui
```

### Working with Tasks
```bash
# Start working on a task (move to current)
sc task start implement-oauth-0127-AB

# Complete a task (move to archive)
sc task complete implement-oauth-0127-AB

# View a task
sc task get implement-oauth-0127-AB

# Update task metadata
sc task update implement-oauth-0127-AB --status "🔴 Blocked"

# Update a specific section
sc task update-section implement-oauth-0127-AB instruction "New instructions here"
```

### Listing Tasks
```bash
# List current tasks (default)
sc task list

# List backlog tasks
sc task list --workflow backlog

# List all tasks including archived
sc task list --all

# Filter by type, status, or area
sc task list --type bug --status "🔵 In Progress"
```

## 📁 Task Structure

Each task is a `.task.md` file with:

1. **Frontmatter**: Type, status, area, and custom fields
2. **Sections**:
   - **Instruction**: What needs to be done
   - **Tasks**: Checklist of subtasks
   - **Deliverable**: Work outputs
   - **Log**: Execution history

## 🔧 Complex Tasks

For large tasks, create a folder with subtasks:

```bash
# Create a complex task
sc task create --title "Dashboard Redesign" --complex

# Add subtasks (numbered for sequencing)
sc task add-subtask dashboard-redesign "01-user-research"
sc task add-subtask dashboard-redesign "02-implement-ui"
sc task add-subtask dashboard-redesign "03-test-implementation"
```

## 💡 Tips

1. **Keep current small**: Only tasks actively being worked on
2. **Review backlog regularly**: Prioritize and prune
3. **Archive monthly**: Tasks are auto-organized by YYYY-MM
4. **Use templates**: Ensure consistency across similar tasks
5. **Update logs**: Document progress in the Log section

## 🔗 Task References

Reference other tasks using: `@task:implement-oauth-0127-AB`
Reference specific sections: `@task:implement-oauth-0127-AB#deliverable`

---

For more information, visit the [Scopecraft documentation](https://github.com/timmeeuwissen/scopecraft).
