package ir.windroida.app.ui

import android.view.View

/** One full screen of the native app. The activity keeps a stack of them. */
abstract class Screen {
    abstract val view: View
    open fun onShow() {}                 // became the visible (top) screen
    open fun onHide() {}                 // covered by another screen
    open fun onDestroy() {}              // removed from the stack
    open fun onBack(): Boolean = false   // true = handled (e.g. closed a panel)
}
