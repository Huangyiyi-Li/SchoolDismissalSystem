package cn.xxt.dismissal.poc;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;

import java.net.URI;

/** Connection bootstrap only. Business settings still come from the platform. */
final class PlatformEndpoint {
    private final SharedPreferences prefs;

    PlatformEndpoint(Context context) {
        prefs = context.getSharedPreferences("platform_connection", Context.MODE_PRIVATE);
    }

    String baseUrl() {
        return prefs.getString("url", BuildConfig.TEST_PLATFORM_URL).replaceAll("/+$", "");
    }

    String token() {
        return prefs.getString("token", BuildConfig.DEVICE_REPORT_TOKEN);
    }

    String hostForDisplay() {
        try { return new URI(baseUrl()).getHost(); }
        catch (Exception error) { return "未连接"; }
    }

    static String[] parsePairUri(Uri link) {
        if (link == null || !"xxtdismissal".equals(link.getScheme())
                || !"connect".equals(link.getHost())) {
            throw new IllegalArgumentException("不是放学联调平台的配对链接");
        }
        String url = link.getQueryParameter("url");
        String token = link.getQueryParameter("token");
        validate(url, token);
        return new String[] {url.replaceAll("/+$", ""), token};
    }

    void save(String url, String token) {
        validate(url, token);
        if (!prefs.edit().putString("url", url.replaceAll("/+$", ""))
                .putString("token", token).commit()) {
            throw new IllegalStateException("平台连接信息保存失败");
        }
    }

    private static void validate(String url, String token) {
        try {
            URI parsed = new URI(url);
            if (!"https".equalsIgnoreCase(parsed.getScheme()) || parsed.getHost() == null
                    || parsed.getUserInfo() != null || parsed.getQuery() != null
                    || parsed.getFragment() != null || parsed.getPath() != null
                    && !parsed.getPath().isEmpty() && !"/".equals(parsed.getPath())) {
                throw new IllegalArgumentException("平台地址必须是 HTTPS 站点根地址");
            }
        } catch (java.net.URISyntaxException error) {
            throw new IllegalArgumentException("平台地址格式无效", error);
        }
        if (token == null || !token.matches("[0-9a-f]{48}")) {
            throw new IllegalArgumentException("配对令牌无效");
        }
    }
}
