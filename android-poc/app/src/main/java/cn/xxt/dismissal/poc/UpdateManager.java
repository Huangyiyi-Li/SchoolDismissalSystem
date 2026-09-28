package cn.xxt.dismissal.poc;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.net.Uri;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.util.Arrays;

/** Download and verify an update before handing it to Android's installer. */
final class UpdateManager {
    private static final long MAX_APK_BYTES = 40L * 1024 * 1024;
    private final Context context;
    private final PlatformEndpoint endpoint;

    UpdateManager(Context context, PlatformEndpoint endpoint) {
        this.context = context;
        this.endpoint = endpoint;
    }

    boolean isNewer(JSONObject release) {
        return release != null && release.optInt("versionCode") > BuildConfig.VERSION_CODE;
    }

    Uri downloadAndVerify(JSONObject release) throws Exception {
        String path = release.getString("downloadPath");
        String sha256 = release.getString("sha256");
        long size = release.getLong("size");
        int code = release.getInt("versionCode");
        if (!path.matches("/api/releases/[0-9a-f]{64}\\.apk")
                || !sha256.matches("[0-9a-f]{64}") || !path.contains(sha256)
                || size < 1 || size > MAX_APK_BYTES || code <= BuildConfig.VERSION_CODE
                || !context.getPackageName().equals(release.getString("packageName"))) {
            throw new IllegalArgumentException("平台升级信息无效");
        }
        File temporary = new File(context.getCacheDir(), "update-download.apk");
        File ready = new File(context.getCacheDir(), "update.apk");
        HttpURLConnection connection = (HttpURLConnection) new URL(endpoint.baseUrl() + path).openConnection();
        try {
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(20000);
            connection.setRequestProperty("X-Device-Token", endpoint.token());
            if (connection.getResponseCode() != 200) {
                throw new IllegalStateException("下载升级包 HTTP " + connection.getResponseCode());
            }
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            long received = 0;
            try (InputStream input = connection.getInputStream();
                 FileOutputStream output = new FileOutputStream(temporary)) {
                byte[] buffer = new byte[65536];
                int count;
                while ((count = input.read(buffer)) != -1) {
                    received += count;
                    if (received > size) throw new IllegalStateException("升级包超过平台声明大小");
                    digest.update(buffer, 0, count);
                    output.write(buffer, 0, count);
                }
            }
            if (received != size || !toHex(digest.digest()).equals(sha256)) {
                throw new IllegalStateException("升级包大小或 SHA-256 校验失败");
            }
            verifyPackage(temporary, code);
            Files.move(temporary.toPath(), ready.toPath(), StandardCopyOption.REPLACE_EXISTING);
            return Uri.parse("content://" + context.getPackageName() + ".updates/update.apk");
        } finally {
            connection.disconnect();
            if (temporary.exists()) temporary.delete();
        }
    }

    private void verifyPackage(File apk, int expectedCode) throws Exception {
        PackageManager manager = context.getPackageManager();
        PackageInfo archive = manager.getPackageArchiveInfo(
                apk.getAbsolutePath(), PackageManager.GET_SIGNING_CERTIFICATES);
        PackageInfo installed = manager.getPackageInfo(
                context.getPackageName(), PackageManager.GET_SIGNING_CERTIFICATES);
        if (archive == null || !context.getPackageName().equals(archive.packageName)
                || archive.getLongVersionCode() != expectedCode || archive.signingInfo == null
                || installed.signingInfo == null) {
            throw new IllegalStateException("升级包包名、版本或签名信息无效");
        }
        Signature[] updateSigners = archive.signingInfo.getApkContentsSigners();
        Signature[] installedSigners = installed.signingInfo.getApkContentsSigners();
        if (!Arrays.equals(updateSigners, installedSigners)) {
            throw new IllegalStateException("升级包签名与已安装应用不一致");
        }
    }

    private static String toHex(byte[] bytes) {
        char[] digits = "0123456789abcdef".toCharArray();
        StringBuilder value = new StringBuilder(bytes.length * 2);
        for (byte item : bytes) {
            value.append(digits[(item >> 4) & 0x0f]);
            value.append(digits[item & 0x0f]);
        }
        return value.toString();
    }
}
