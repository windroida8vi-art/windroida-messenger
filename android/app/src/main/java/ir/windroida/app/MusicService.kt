package ir.windroida.app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.drawable.Icon
import android.media.MediaMetadata
import android.media.session.MediaSession
import android.media.session.PlaybackState
import android.os.Build
import android.os.IBinder
import ir.windroida.app.ui.VoicePlayer

/**
 * Makes the phone recognise the player: a system MediaSession (lock screen, quick-settings media card, Bluetooth / headset buttons,
 * car) plus the media notification with previous / play-pause / next / close. It only mirrors the process-wide VoicePlayer and
 * forwards the buttons to it, so it works even when the app screen is closed. It stops itself when nothing is playing.
 */
class MusicService : Service() {
    private var session: MediaSession? = null
    private var vp: VoicePlayer? = null
    private val onState: () -> Unit = { refresh() }

    companion object {
        private const val CH = "music"
        private const val ID = 4001
        fun start(c: Context) {
            try { c.startForegroundService(Intent(c, MusicService::class.java)) } catch (_: Exception) {}
        }
    }

    override fun onBind(i: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        getSystemService(NotificationManager::class.java).createNotificationChannel(NotificationChannel(CH, "پخش موسیقی", NotificationManager.IMPORTANCE_LOW).also { it.setSound(null, null) })
        val s = MediaSession(this, "Windroida")
        s.setCallback(object : MediaSession.Callback() {
            override fun onPlay() { vp?.let { if (!it.isPlaying) it.toggleCurrent() } }
            override fun onPause() { vp?.let { if (it.isPlaying) it.toggleCurrent() } }
            override fun onSkipToNext() { vp?.next() }
            override fun onSkipToPrevious() { vp?.prev() }
            override fun onSeekTo(pos: Long) { vp?.seekMs(pos) }
            override fun onStop() { vp?.stop() }
        })
        s.isActive = true
        session = s
        vp = VoicePlayer.peek()
        vp?.addStateListener(onState)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val v = vp ?: VoicePlayer.peek().also { vp = it; it?.addStateListener(onState) }
        when (intent?.action) {
            "pp" -> v?.toggleCurrent()
            "next" -> v?.next()
            "prev" -> v?.prev()
            "stop" -> v?.stop()
        }
        refresh(true)
        return START_NOT_STICKY
    }

    private fun pi(action: String, req: Int): PendingIntent =
        PendingIntent.getService(this, req, Intent(this, MusicService::class.java).setAction(action), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)

    private fun refresh(force: Boolean = false) {
        val v = vp
        val s = session ?: return
        if (v == null || v.playingId == 0L) {
            // nothing plays (any more): leave. A service started with startForegroundService() MUST call startForeground() first,
            // otherwise Android kills the app, so a tiny notification is posted and removed again right away.
            try {
                val n = Notification.Builder(this, CH).setSmallIcon(android.R.drawable.ic_media_play).setContentTitle("Windroida").build()
                if (Build.VERSION.SDK_INT >= 29) startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK) else startForeground(ID, n)
                stopForeground(true)
            } catch (_: Exception) {}
            stopSelf()
            return
        }
        val playing = v.isPlaying
        val dur = v.durationMs.toLong()
        s.setMetadata(MediaMetadata.Builder().putString(MediaMetadata.METADATA_KEY_TITLE, v.title).putString(MediaMetadata.METADATA_KEY_ARTIST, v.subtitle)
            .putLong(MediaMetadata.METADATA_KEY_DURATION, if (dur > 0) dur else -1L).build())
        val st = when { v.loading -> PlaybackState.STATE_BUFFERING; playing -> PlaybackState.STATE_PLAYING; else -> PlaybackState.STATE_PAUSED }
        s.setPlaybackState(PlaybackState.Builder()
            .setActions(PlaybackState.ACTION_PLAY or PlaybackState.ACTION_PAUSE or PlaybackState.ACTION_PLAY_PAUSE or PlaybackState.ACTION_SKIP_TO_NEXT or
                PlaybackState.ACTION_SKIP_TO_PREVIOUS or PlaybackState.ACTION_SEEK_TO or PlaybackState.ACTION_STOP)
            .setState(st, v.positionMs.toLong(), if (playing) 1f else 0f).build())
        val open = PendingIntent.getActivity(this, 5, Intent(this, if (Prefs.mode(this) == "web") MainActivity::class.java else NativeActivity::class.java)
            .addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        fun act(icon: Int, title: String, action: String, req: Int) = Notification.Action.Builder(Icon.createWithResource(this, icon), title, pi(action, req)).build()
        val b = Notification.Builder(this, CH)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentTitle(v.title)
            .setContentText(v.subtitle)
            .setContentIntent(open)
            .setOngoing(playing)
            .setShowWhen(false)
            .setVisibility(Notification.VISIBILITY_PUBLIC)
            .addAction(act(android.R.drawable.ic_media_previous, "قبلی", "prev", 1))
            .addAction(act(if (playing) android.R.drawable.ic_media_pause else android.R.drawable.ic_media_play, if (playing) "توقف" else "پخش", "pp", 2))
            .addAction(act(android.R.drawable.ic_media_next, "بعدی", "next", 3))
            .addAction(act(android.R.drawable.ic_menu_close_clear_cancel, "بستن", "stop", 4))
            .setStyle(Notification.MediaStyle().setMediaSession(s.sessionToken).setShowActionsInCompactView(0, 1, 2))
            .setDeleteIntent(pi("stop", 6))
        val n = b.build()
        if (Build.VERSION.SDK_INT >= 29) startForeground(ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK) else startForeground(ID, n)
    }

    override fun onDestroy() {
        vp?.removeStateListener(onState)
        try { session?.isActive = false; session?.release() } catch (_: Exception) {}
        session = null
        super.onDestroy()
    }
}
