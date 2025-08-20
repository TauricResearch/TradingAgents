#!/bin/bash
main() {
    case "$1" in
        "test")
            echo "test works"
            ;;
        *)
            echo "unknown command"
            ;;
    esac
}
main "$@"
