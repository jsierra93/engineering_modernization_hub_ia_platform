#!/bin/sh
# packages/backend/entrypoint.sh
#
# backstage-cli's dev server (repo start / package start) binds the
# frontend dev server to loopback only ("Loopback: http://localhost:3000/")
# -- confirmed empirically, 2026-09-26, with no CLI flag, app-config key
# (app.listen.host) or env var (HOST) able to change it in this version.
# That is fine on a host machine (localhost IS reachable there) but breaks
# through Docker's port mapping, which forwards to the container's
# external interface, never its loopback.
#
# socat bridges the gap: it listens on 0.0.0.0:3000 (a distinct bind from
# the dev server's own 127.0.0.1:3000 -- both can coexist) and forwards
# every connection to the dev server's real loopback address. Nothing
# about the frontend build itself changes; this is purely a network
# rendezvous fix.
set -e

socat TCP-LISTEN:3000,bind=0.0.0.0,fork,reuseaddr TCP:127.0.0.1:3000 &

exec pnpm start
