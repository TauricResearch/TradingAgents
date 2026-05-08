---
title: "How I Use Just to Quickly Organize Project-Level Commands"
author: "Chandler"
site: "DEV Community"
published: 2023-01-26T20:34:44Z
source: "https://dev.to/casualcoders/just-the-best-way-to-handle-project-level-scripting-k4g"
domain: "dev.to"
language: "en"
description: "Have you ever had a folder full of random scripts you used for automation? Have you ever tried to use... Tagged with devmeme, watercooler."
word_count: 974
---

Have you ever had a folder full of random scripts you used for automation? Have you ever tried to use a Makefile to script things? Or even put a bunch of run options in your `package.json` file? If so, you may have found that these tools lack the simplicity and ease-of-use that you need to automate your tasks effectively. That's where Just comes in.

## A passive-aggressive way to run things.

Just is a command-line tool that provides a simple and easy way to run scripts and commands. It is similar to make in that it allows you to specify dependencies between commands, but it is more focused on running scripts and commands, rather than building and compiling software.

Just also provides some additional features such as parallel execution, caching, and error handling. It is designed to be easy to use and requires minimal setup, making it a useful tool for automating repetitive tasks.

## Installation

If you have homebrew, its quite simple:

```
$ brew install just
```

If you have rust installed its also quite easy:

```
$ cargo install just
```

Its also available on various other \*nix and Windows [package managers](https://just.systems/man/en/chapter_4.html), and as a [Unix binary](https://just.systems/man/en/chapter_5.html).

## Examples

Here's an example of a simple justfile that demonstrates how to use Just to automate a few tasks (called recipes in their docs):

```
# Justfile

# This command runs the "clean" task before running the "build" task
build: clean
    echo "Building project..."
    # commands to build the project go here

# This command runs the "clean" task before running the "test" task
test: clean
    echo "Running tests..."
    # commands to run tests go here

clean:
    echo "Cleaning project..."
    # commands to clean the project go here

# This command can be run independently
deploy:
    echo "Deploying project..."
    # commands to deploy the project go here
```

You can execute the tasks defined in the justfile by running the command `just <taskname>`. For example, to run the `build` task, you would run `just build`. Just will automatically run any tasks that the task you're running depends on, in the order they're defined in the file.

In this example, you can see that the task `build` and `test` depends on the task `clean`, so if you run `just build` or `just test`, Just will run `clean` before running the task you requested.

You can also run the task `deploy` independently and it doesn't have any dependencies.

You can also add comments in your justfile using the `#` character, as shown in this example.

This is a simple example, but you can use Just to automate much more complex tasks and scripts.

Here is an example of a script I wrote for one of my projects:

```
# builds the docker image
build-docker:
    #!/bin/bash
    set -euo pipefail
    ARCH=$(uname -m)
    if [ $ARCH = "aarch64" ]; then
      ARCH="arm64"
    fi
    if [ $ARCH = "x86_64" ]; then
      ARCH="amd64"
    fi
    docker build -f docker/Dockerfile.$ARCH -t ceres .

# runs the executable in docker
run-docker mode="stout": check
    docker run --rm -p 8080:8080 -v $(pwd)/config:/app/config ceres --mode {{mode}}

# starts the daemon. Specify mode=prod to run in production mode (without grafana)
up mode="dev": build-docker check
    docker compose -f docker/docker-compose-{{mode}}.yml up -d

# shows daemon logs
logs mode="dev":
    docker compose -f docker/docker-compose-{{mode}}.yml logs -f

# stops the daemon
down mode="dev":
    docker compose -f docker/docker-compose-{{mode}}.yml down
```

With just you can add parameters to the scripts that you define, along with defaults. You can also specify an interpreter for your scripts. Bash and Zsh common ones, but I’ve even seen Python scripts written in a Justfile!

## Good Practices

One piece of good practice is to define the `default` behavior, which is what happens when you run `just` without any additional commands. Here is what I usually write:

```
default:
    just --list --unsorted
```

When I run this in a project that has other scripts defined with comments, this is the output.

```
$ just
Available recipes:
    build                        # builds the executable
    build-docker                 # builds the docker image
    clean                        # cleans the build artifacts
    compile                      # alias for build
    default                      # default task
    down mode="dev"              # stops the daemon
    dump                         # runs the executable in dump mode
    fmt                          # Formats the project
    format                       # Alias for fmt
    logs mode="dev"              # shows daemon logs
    run *json                    # runs the executable in stout mode
    run-docker mode="stout"      # runs the executable in docker
    serve                        # runs the executable in serve mode
    up mode="dev"                # starts the daemon. Specify mode=prod to run in production mode (without grafana)
```

## Hidden Tasks

You can also hide tasks from the list output with either a leading underscore or the `[private]` tag. Here is an example of both:

```
[private]
check:
    #!/bin/bash
    set -euo pipefail
    if [ ! -f config/optional.json ]; then
      echo "Optional 'optional.json' file is missing."
    fi
    if [ ! -f config/required.json ]; then
      echo "Please add a 'required.json\` file."
      exit 1
    fi

_helper:
    echo "This is a hidden task"
```

Notice how in the above output, these are missing? They’re in my project’s Justfile, but they’re hidden as they are utility tasks I don’t want other devs to run.

## Silent Tasks

If you don’t want a task to echo the commands, you can add an `@` symbol before the command.

```
@quiet: # from the Just manual
  echo hello
  echo goodbye
  @# all done!
```

The `@` symbol can also be used to invert the echo. For example, you can use `@` to not echo certain commands in a normal task:

```
loud:
    echo "Hello"
    @echo "This is a test"
```

## Conclusion

I hope you found this blog post helpful! I found that after I was introduced to Justfiles I use them for all my scripts in my projects! How do you normally keep track of your scripts and repetitive tasks in your projects? Will you use Just from now on? Leave a comment down below telling me about it! Happy coding!