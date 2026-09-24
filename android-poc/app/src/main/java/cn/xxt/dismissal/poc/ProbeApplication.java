package cn.xxt.dismissal.poc;

import android.app.Application;

import j2a.awt.AwtEnv;
import onbon.bx06.Bx6GEnv;

/** Vendor Android SDK needs its java.awt shim linked before any LED operation. */
public final class ProbeApplication extends Application {
    static Exception sdkFailure;

    @Override
    public void onCreate() {
        super.onCreate();
        try {
            AwtEnv.link(this);
            AwtEnv.configPaintAntiAliasFlag(false);
            Bx6GEnv.initial();
        } catch (Exception error) {
            sdkFailure = error;
        }
    }
}
