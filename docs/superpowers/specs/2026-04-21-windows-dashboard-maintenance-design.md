# Windows Dashboard Maintenance Redesign

**Date:** 2026-04-21
**Project:** School Dismissal System
**Platform:** Windows desktop client, low-spec host, 24/7 unattended operation

## Summary

This redesign keeps the current native `PyQt6` desktop architecture and upgrades the product into a formal unattended terminal experience. The system will present a full-screen-friendly guard dashboard during daily operation and hide operational controls behind a protected maintenance mode.

The redesign must improve aesthetics and readability without introducing a browser runtime, a web shell, or heavy background processes. All visual upgrades must stay within Qt-native capabilities and must remain appropriate for a low-memory Windows machine that runs continuously.

## Context

The current application already fits the core technical constraints:

- native Windows desktop application
- low runtime overhead compared with browser-based shells
- existing integration with UDP, SQLite, API sync, and Windows TTS

The current weaknesses are mainly in presentation and operational safety:

- the main window looks like an internal tool rather than a 24/7 duty terminal
- the interface exposes too many operational controls during normal watching
- status information is present but not prioritized for quick scanning
- service health is not modeled clearly enough for long-running failure visibility
- some service/config logic is inconsistent, which makes future maintenance harder

## Goals

1. Turn the application into a clear, attractive, professional-looking duty dashboard.
2. Preserve a native, low-overhead Windows deployment model.
3. Reduce accidental operator interaction during school use.
4. Make critical failures visible from a distance.
5. Improve maintainability and stability in the same pass, especially around Windows runtime behavior.

## Non-Goals

This redesign does not include:

- replacing the app with Electron, WebView, or any browser-based UI stack
- introducing a large runtime beyond the existing Python/Qt packaging model
- splitting the app into a complex multi-process architecture
- adding remote admin panels or cloud management consoles
- introducing heavy charts or non-essential visual effects
- performing a broad database redesign beyond what is needed for this feature set

## Chosen Architecture

The product remains a single native `PyQt6` Windows application with the current service-layer responsibilities preserved:

- UDP listener service
- TTS broadcast service
- API sync service
- local SQLite persistence
- desktop UI shell

The redesign changes the UI and state boundaries, not the deployment model.

### Why This Architecture

This choice best satisfies the confirmed user constraints:

- the client must remain independent and not run in a browser
- school staff should not be tempted to close or misuse a browser window
- the host machine is low-spec and can not safely carry a large browser runtime
- the system must run 24 hours a day with predictable resource usage

## User Experience Model

The product is explicitly divided into two modes.

### 1. Guard Dashboard Mode

This is the default mode and the mode used during ordinary school operation.

Characteristics:

- opens into a large, dashboard-like main view
- suitable for maximized use on a `1920×1080` display
- emphasizes three primary signals:
  - device online status
  - recent swipe/broadcast logs
  - whether the current time is inside the dismissal window
- avoids exposing routine admin actions in the visible surface
- supports long-duration viewing without visual clutter

### 2. Maintenance Mode

This mode is only for administrators.

Characteristics:

- not visible by default
- entered through a hidden trigger
- protected by a lightweight 4-digit access code
- contains operational controls and settings
- automatically times out back into guard mode after inactivity

## Dashboard Visual Direction

The approved visual direction is a **control-center** style rather than a soft campus notice-board style.

Visual rules:

- dark background with restrained gradients
- high-contrast state colors
- strong card hierarchy
- crisp typography
- subtle glow/highlight edges only where they improve scanning
- no heavy animation system
- no decorative elements that compete with status information

The aesthetic target is “professional unattended terminal,” not “consumer app.”

## Dashboard Layout

The approved layout is a **wide-focus** layout designed for a `1920×1080` horizontal screen.

### Top Status Band

The top band shows:

- current time
- current dismissal-window state
- overall system state
- maintenance-mode availability or lock state

Behavior:

- normal state remains visually quiet
- abnormal state changes the band into a warning treatment
- warning treatment may include a lightweight blink/pulse effect implemented with cheap Qt-native styling changes only

### Summary Cards

Below or integrated with the top region, three summary cards show:

- runtime status
- online device count
- current dismissal time window

These are not interactive controls. They are quick-read status surfaces.

### Main Center Region

The central dominant region is the **recent swipe log**.

Reasoning:

- it is the most frequently watched information stream
- it benefits from width and readable row spacing
- it is the most important continuous narrative for the on-duty operator

### Right Status Column

The right column contains stacked status cards:

- abnormal alerts
- device health
- system notices

The abnormal alert card always stays at the top and visually dominates the column whenever any active fault exists.

## Fault Visibility Rules

The user requested strong alerting.

Therefore, the dashboard must implement the following severity behavior:

- **Normal:** neutral or low-saturation state styling
- **Warning:** obvious color change and surfaced detail text
- **Critical:** promote the alert to the top, intensify visual emphasis, and apply a lightweight blinking/pulsing treatment

Fault types that must be representable in the UI:

- UDP listener failed or stopped
- TTS playback errors
- repeated API sync or push failures
- device offline conditions
- invalid or missing required runtime configuration

The alert system must be explicit and stateful. It must not rely only on `print` output.

## Maintenance Mode Design

Maintenance mode is a hidden operational layer rather than a second heavyweight application.

### Entry

Approved entry behavior:

- hidden trigger such as a keyboard shortcut or special corner interaction
- follow-up 4-digit code entry dialog

The trigger should be easy for trained administrators but invisible to ordinary users.

### Contents

Maintenance mode must contain:

- school binding/configuration
- device management
- dismissal-time configuration
- manual sync trigger
- test mode switch
- access to detailed logs or diagnostics

### Exit Behavior

Maintenance mode must automatically return to guard mode after a short inactivity window, targeted at roughly 3-5 minutes. The exact timeout can be implemented as a configuration constant or UI-level setting, but the default behavior must be automatic return.

## Stability and Maintainability Work Included

This redesign is not only a skin change. It also includes targeted service-layer hardening.

### State Modeling

The system needs a clearer internal health/state model so that UI rendering does not depend on ad-hoc `print` output or scattered local flags.

Expected direction:

- define explicit runtime state for UDP listener
- define explicit runtime state for sync/API status
- define explicit runtime state for TTS/broadcast health
- aggregate these into a dashboard-readable application status model

### Windows TTS Hardening

The Windows TTS path must be reviewed and tightened so that:

- thread ownership is clear
- initialization and cleanup are predictable
- repeated broadcasts do not degrade the worker over long uptime
- fault states can be surfaced to the UI

### Config Consistency

Configuration behavior must be made internally consistent:

- settings exposed in the UI must have a real runtime effect
- dead or partially used configuration entries should be corrected or removed
- settings changes that affect runtime services should be clearly propagated

### Service/UI Decoupling

The UI should subscribe to structured status and log updates rather than infer behavior indirectly. This will make later maintenance and testing easier without requiring a full architecture rewrite.

## Scope Boundaries for This Redesign

### Included

- main window redesign into guard dashboard mode
- protected maintenance mode
- dashboard status model improvements
- Windows long-running stability improvements in the current service layer
- targeted automated tests for logic-heavy parts

### Excluded

- browser-shell or web-based UI replacement
- multi-process refactor
- large infrastructure migration
- advanced analytics/reporting views
- remote operation features

## Verification Strategy

The redesign must be validated in four layers.

### 1. Windows Runtime Validation

Confirm that the packaged Windows application:

- starts reliably
- restores/maximizes correctly
- remains stable during long idle/runtime periods
- can transition between guard mode and maintenance mode correctly

### 2. Service Stability Validation

Confirm that:

- UDP listening still works reliably
- TTS still speaks correctly on Windows
- API sync/push failures become visible in the dashboard
- service failures recover or surface clearly instead of failing silently

### 3. UI Behavior Validation

Confirm that:

- guard mode is the default view
- the three core information groups remain visible and readable
- maintenance mode is hidden and protected
- maintenance mode auto-exits after inactivity
- critical alerts visually override normal dashboard calmness

### 4. Automated Test Coverage

Prefer tests for logic that does not need fragile GUI automation, such as:

- dismissal-window evaluation
- runtime status aggregation
- alert severity mapping
- configuration propagation rules
- inactivity timeout logic where practical

## Success Criteria

The redesign is successful when all of the following are true:

- the app still feels lightweight and stable on a low-spec Windows machine
- the main window now reads as a professional duty terminal
- a distant observer can immediately identify whether the system is healthy
- school staff are discouraged from entering admin operations by default
- administrators can still access maintenance tasks quickly when needed
- the underlying code becomes easier to maintain because state and service behavior are clearer

## Implementation Approach

Implementation should proceed as a focused redesign rather than a full rewrite:

1. define the runtime status model and dashboard data surface
2. refactor the main window into guard mode structure
3. introduce protected maintenance mode
4. harden Windows service behavior where the UI now depends on explicit status
5. add targeted tests for the extracted logic

This sequencing keeps the native deployment model intact while improving both appearance and operational reliability.
