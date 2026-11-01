# UI library provenance

The application does **not** depend on an official Samsung One UI component
library. It is a native adaptation of Samsung's public design guidance.

| Surface | Actual dependency | Source in this repository |
| --- | --- | --- |
| Android | Google Material Components `1.12.0`, AndroidX AppCompat `1.7.0`, custom themes and layouts | `android/app/build.gradle.kts`, `android/app/src/main/res/` |
| Desktop | PySide6 `6.11.2` / Qt, custom app-owned stylesheet and widgets | `server/gui/theme.py`, `server/gui/`, `server/widgets/` |

[Samsung's official One UI developer site](https://developer.samsung.com/one-ui/index.html)
publishes design guidelines. Its public guidance is the visual reference; this
is not evidence that Samsung distributes a corresponding Android or Qt SDK.
The reviewed official pages did not identify an official Qt component kit.

[OneUIProject](https://github.com/OneUIProject/oneui-design) is a separate
community project, not an official Samsung distribution, and is not installed in
this application. Its project README alone cannot substantiate a claim that an
application uses Samsung's latest official library.

Samsung's [current One UI product page](https://www.samsung.com/us/apps/one-ui/)
describes the firmware experience. A firmware release version must not be used
as the version number of the custom application theme or its dependencies.

The previous rewrite should be described as **One UI-inspired native UI**, not
“official latest One UI library integration.” Layout v2 keeps this distinction
explicit and does not add or relabel third-party components as official.
