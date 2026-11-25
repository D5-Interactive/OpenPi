"""Command line: `openpi` opens the app; the rest are small operators' helpers."""

from __future__ import annotations

from pathlib import Path

import click

from openpi import config


class OpenpiGroup(click.Group):
    """Ensure ~/.openpi exists on every invocation, not just when the GUI opens."""

    def invoke(self, ctx: click.Context):
        config.ensure_home()
        return super().invoke(ctx)


@click.group(cls=OpenpiGroup, invoke_without_command=True)
@click.option("--project", type=click.Path(file_okay=False), default=None,
              help="folder to open (default: current folder)")
@click.option("--session-root", type=click.Path(file_okay=False), envvar="OPENPI_SESSION_ROOT",
              help="pi session directory (default: ~/.pi/agent/sessions)")
@click.option("--connect", metavar="URL", help="connect to a running `openpi serve` instead of "
              "spawning pi locally (e.g. http://host:7717)")
@click.option("--token", help="server token for --connect (or put ?token= in the URL)")
@click.option("--tls-ca", type=click.Path(exists=True, dir_okay=False),
              help="CA/cert file to trust when --connect is https:// (the server's self-signed cert)")
@click.pass_context
def main(ctx: click.Context, project: str | None, session_root: str | None,
         connect: str | None, token: str | None, tls_ca: str | None) -> None:
    """Desktop control room for the pi coding agent.

    `openpi` opens the app in the current folder; `openpi --project PATH` opens PATH.
    """
    if ctx.invoked_subcommand is not None:
        return
    from .ui.app import launch

    if project and not Path(project).is_dir():
        raise click.BadParameter(f"not a directory: {project}", param_hint="--project")
    ctx.exit(launch(project=project, session_root=session_root, connect=connect, token=token,
                    tls_ca=tls_ca))


@main.command()
@click.option("--session-root", type=click.Path(file_okay=False))
@click.option("--limit", default=20, show_default=True)
def sessions(session_root: str | None, limit: int) -> None:
    """List pi sessions on disk."""
    from pathlib import Path

    from .pi.index import default_session_dir, scan

    metas = scan(Path(session_root) if session_root else default_session_dir())
    if not metas:
        click.echo("no sessions found")
        return
    for meta in metas[:limit]:
        flag = "*" if meta.name else " "
        click.echo(f"{flag} {meta.id[:8]}  {meta.cwd}\n  {meta.title[:90]}")


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=7717, show_default=True, type=int)
@click.option("--cwd", type=click.Path(file_okay=False), help="default folder for new sessions")
@click.option("--token", envvar="OPENPI_SERVER_TOKEN", help="access token (default: generated)")
@click.option("--trust/--no-trust", default=False,
              help="load project-local pi resources in every project")
@click.option("--relay", help="relay host:port of its instance listener (e.g. relay.example.com:7719)")
@click.option("--relay-token", envvar="OPENPI_RELAY_TOKEN", help="token shared with the relay")
@click.option("--tls/--no-tls", default=False,
              help="serve HTTPS with a self-signed cert (end-to-end encryption through the relay)")
def serve(host: str, port: int, cwd: str | None, token: str | None, trust: bool,
          relay: str | None, relay_token: str | None, tls: bool) -> None:
    """Run the background web server (browser + relay access)."""
    from .server.serve import run

    raise SystemExit(run(host=host, port=port, cwd=cwd, token=token, trust=trust,
                         relay=relay, relay_token=relay_token, tls=tls))


@main.command()
@click.option("--public-port", default=7718, show_default=True, type=int,
              help="port browsers connect to")
@click.option("--instance-port", default=7719, show_default=True, type=int,
              help="port the openpi server dials out to")
@click.option("--token", envvar="OPENPI_RELAY_TOKEN", required=True,
              help="shared secret; also pass it to `openpi serve --relay-token`")
@click.option("--host", default="0.0.0.0", show_default=True)
def relay(public_port: int, instance_port: int, token: str, host: str) -> None:
    """Run a relay so a server behind NAT is reachable without an open port."""
    import time

    from .relay import start_relay

    actual_public, actual_instance, _thread, _loop = start_relay(
        token, public_port, instance_port, host)
    click.echo(f"relay public   {host}:{actual_public}")
    click.echo(f"relay instance {host}:{actual_instance}  (openpi serve --relay host:{actual_instance})")
    click.echo("ctrl-c to stop")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


@main.group()
def token() -> None:
    """Manage per-device tokens for a server."""


@token.command("new")
@click.option("--name", default="", help="label for the device")
def token_new(name: str) -> None:
    """Issue a token. The server picks it up without a restart."""
    from openpi import config

    pairing = config.Pairings().add(name)
    click.echo(f"id:    {pairing.id}")
    click.echo(f"name:  {pairing.name or '(no name)'}")
    click.echo(f"token: {pairing.token}")


@token.command("list")
def token_list() -> None:
    """List issued device tokens (the tokens themselves are not shown)."""
    from openpi import config

    for pairing in config.Pairings().list():
        click.echo(f"{pairing.id}  {pairing.name or '(no name)'}")


@token.command("revoke")
@click.argument("pairing_id")
def token_revoke(pairing_id: str) -> None:
    """Revoke a device token by id."""
    from openpi import config

    if not config.Pairings().revoke(pairing_id):
        click.echo("no such pairing")
        raise SystemExit(1)
    click.echo("revoked")


@main.command()
def setup() -> None:
    """Create ~/.openpi and install/update the pi coding agent."""
    from openpi import config
    from openpi.pi.install import ensure_pi, installed_version, latest_version

    home = config.ensure_home()
    click.echo(f"home:     {home}")
    before = installed_version()
    binary = ensure_pi(update=True)
    click.echo(f"pi:       {before or 'not installed'} -> {installed_version(binary)}")
    click.echo(f"latest:   {latest_version() or 'unknown (no network?)'}")


@main.command()
def doctor() -> None:
    """Check the pi binary, version, models, and session directory."""
    from .pi.doctor import probe
    from .pi.index import default_session_dir, scan
    from .pi.install import installed_version, latest_version

    root = default_session_dir()
    report = probe()
    click.echo(f"binary:        {report['binary']}")
    click.echo(f"version:       {report['version'] or 'unknown'}")
    latest = latest_version()
    click.echo(f"pi latest:     {latest or 'unknown'}")
    if latest and installed_version() != latest:
        click.echo("               run `openpi setup` to update pi")
    click.echo(f"session dir:   {root} ({len(scan(root))} sessions)")
    if report["ok"]:
        state = report["state"] or {}
        click.echo(f"model:         {state.get('model')} (thinking {state.get('thinking')})")
        click.echo(f"models:        {report['models']} available")
        click.echo(f"thinking:      {', '.join(report['thinking_levels']) or 'none'}")
    else:
        click.echo(f"error:         {report['error'] or 'pi did not answer the RPC probe'}")
        raise SystemExit(1)
