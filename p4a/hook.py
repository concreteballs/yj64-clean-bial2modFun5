from pathlib import Path

from pythonforandroid.toolchain import ToolchainCL


ACTIVITY = 'org.blackmirror.blackmirror.MonitorActivity'
PROCESS = ':monitor_ui'
PROVIDER = 'org.blackmirror.blackmirror.DiagnosticMonitorProvider'
AUTHORITY = 'org.blackmirror.blackmirror.diagnostics'
PERMISSION = 'org.blackmirror.blackmirror.permission.MONITOR_COMMAND'


def after_apk_build(toolchain: ToolchainCL) -> None:
    manifest_file = (
        Path(toolchain._dist.dist_dir)
        / 'src'
        / 'main'
        / 'AndroidManifest.xml'
    )
    text = manifest_file.read_text(encoding='utf-8')

    marker = f'android:name="{ACTIVITY}"'
    position = text.find(marker)
    if position < 0:
        raise RuntimeError(
            f'Cannot find {ACTIVITY} in generated AndroidManifest.xml'
        )
    tag_end = text.find('>', position)
    tag_start = text.rfind('<activity', 0, position)
    if tag_end < 0 or tag_start < 0:
        raise RuntimeError('Cannot locate MonitorActivity manifest tag')
    tag = text[tag_start:tag_end + 1]
    if 'android:process="' not in tag:
        replacement = tag[:-1] + f' android:process="{PROCESS}">'
        text = text[:tag_start] + replacement + text[tag_end + 1:]
    elif f'android:process="{PROCESS}"' not in tag:
        raise RuntimeError('MonitorActivity has an unexpected process assignment')

    if text.count(f'android:name="{PROVIDER}"') > 1:
        raise RuntimeError('Duplicate DiagnosticMonitorProvider declaration')
    if f'android:name="{PROVIDER}"' not in text:
        provider_xml = (
            f'    <provider android:name="{PROVIDER}" '
            f'android:authorities="{AUTHORITY}" android:exported="true" '
            f'android:permission="{PERMISSION}" />\n'
        )
        close = text.rfind('</application>')
        if close < 0:
            raise RuntimeError('Cannot locate closing application tag')
        text = text[:close] + provider_xml + text[close:]

    if text.count(f'android:name="{PERMISSION}"') < 1:
        raise RuntimeError('Base signature permission declaration missing')
    if text.count(f'android:authorities="{AUTHORITY}"') != 1:
        raise RuntimeError('Base provider authority missing or duplicated')

    manifest_file.write_text(text, encoding='utf-8')
    print('YJ-64: MonitorActivity process and authenticated Monitor IPC provider verified')
