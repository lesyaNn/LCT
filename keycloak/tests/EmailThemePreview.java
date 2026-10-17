/* Render the installed Keycloak base templates with the custom layout.
 * No server, credentials, SMTP or new runtime dependencies are needed.
 * See backend/docs/EMAIL_NOTIFICATIONS.md for the invocation.
 */
import freemarker.cache.FileTemplateLoader;
import freemarker.cache.MultiTemplateLoader;
import freemarker.cache.StringTemplateLoader;
import freemarker.cache.TemplateLoader;
import freemarker.core.HTMLOutputFormat;
import freemarker.template.Configuration;
import freemarker.template.TemplateMethodModelEx;
import freemarker.template.TemplateScalarModel;
import java.io.InputStreamReader;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.MessageFormat;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Properties;
import java.util.zip.ZipFile;

class EmailThemePreview {
    private static String value(Object argument) throws Exception {
        return argument instanceof TemplateScalarModel scalar ? scalar.getAsString() : argument.toString();
    }

    private static void loadMessages(ZipFile jar, Properties messages, String language) throws Exception {
        var entry = jar.getEntry("theme/base/email/messages/messages_" + language + ".properties");
        try (var reader = new InputStreamReader(jar.getInputStream(entry), StandardCharsets.UTF_8)) {
            messages.load(reader);
        }
    }

    private static Configuration configuration(TemplateLoader loader) {
        var cfg = new Configuration(Configuration.VERSION_2_3_32);
        cfg.setTemplateLoader(loader);
        cfg.setDefaultEncoding("UTF-8");
        cfg.setOutputFormat(HTMLOutputFormat.INSTANCE);
        cfg.setAutoEscapingPolicy(Configuration.ENABLE_IF_SUPPORTED_AUTO_ESCAPING_POLICY);
        cfg.setLogTemplateExceptions(false);
        return cfg;
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException("Usage: EmailThemePreview.java THEMES.jar EMAIL_THEME_DIR OUTPUT_DIR");
        }
        Path theme = Path.of(args[1]);
        Path output = Path.of(args[2]);
        try (var jar = new ZipFile(args[0])) {
            var base = new StringTemplateLoader();
            var names = new ArrayList<String>();
            for (var entry : jar.stream().filter(e -> e.getName().startsWith("theme/base/email/html/")
                    && e.getName().endsWith(".ftl")).toList()) {
                String name = entry.getName().substring("theme/base/email/html/".length());
                base.putTemplate(name, new String(jar.getInputStream(entry).readAllBytes(), StandardCharsets.UTF_8));
                if (!name.equals("template.ftl")) names.add(name);
            }
            var custom = configuration(new MultiTemplateLoader(new TemplateLoader[] {
                new FileTemplateLoader(theme.resolve("html").toFile()), base
            }));
            var original = configuration(base);
            var index = new StringBuilder("<!doctype html><html lang=\"ru\"><meta charset=\"utf-8\">"
                + "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
                + "<title>Keycloak email previews</title><body style=\"font:16px/1.8 Arial;padding:24px\">"
                + "<h1>Keycloak email previews</h1>");
            for (String language : List.of("ru", "en")) {
                index.append("<h2>").append(language).append("</h2><ul>");
                Files.createDirectories(output.resolve(language).resolve("img"));
                Files.write(output.resolve(language).resolve("img/rostelecom-email.png"),
                    Files.readAllBytes(theme.resolve("resources/img/rostelecom-email.png")));
                var messages = new Properties();
                loadMessages(jar, messages, "en");
                loadMessages(jar, messages, language);
                try (var reader = Files.newBufferedReader(theme.resolve("messages/messages_" + language + ".properties"))) {
                    messages.load(reader);
                }
                var model = new HashMap<String, Object>();
                model.put("locale", Locale.forLanguageTag(language));
                model.put("ltr", true);
                model.put("url", Map.of("resourcesUrl", "."));
                model.put("realmName", "RTK EdTech CRM");
                model.put("link", "https://crm.example.test/action?key=demo-token&client_id=rtk-frontend");
                model.put("linkExpiration", 30);
                model.put("linkExpirationFormatter", (TemplateMethodModelEx) values ->
                    language.equals("ru") ? "30 минут" : "30 minutes");
                model.put("requiredActions", List.of("UPDATE_PASSWORD"));
                model.put("newEmail", "new@example.test");
                model.put("code", "001234");
                model.put("organization", Map.of("name", "ИТ Школа"));
                model.put("firstName", "Анна");
                model.put("lastName", "Петрова");
                model.put("identityProviderDisplayName", "Corporate SSO");
                model.put("identityProviderContext", Map.of("username", "anna@example.test"));
                model.put("credentialScopeDisplayName", "Employee credential");
                model.put("event", Map.of("date", "17.10.2026 12:00", "ipAddress", "192.0.2.1",
                    "getDetail", (TemplateMethodModelEx) values -> "password"));
                model.put("subjectKey", "accountDisableNotificationSubject");
                model.put("messageKey", "accountDisableNotificationBody");
                model.put("user", Map.of("firstName", "Анна", "username", "anna"));
                model.put("daysRemaining", 5);
                model.put("reason", "account inactivity");
                model.put("customMessage", "Custom account notification");
                model.put("msg", (TemplateMethodModelEx) values -> {
                    try {
                        String pattern = messages.getProperty(value(values.get(0)), value(values.get(0)));
                        Object[] arguments = new Object[values.size() - 1];
                        for (int i = 1; i < values.size(); i++) arguments[i - 1] = value(values.get(i));
                        return new MessageFormat(pattern, Locale.forLanguageTag(language)).format(arguments);
                    } catch (Exception e) { throw new RuntimeException(e); }
                });
                // Trusted demo fixtures only. The inherited production templates still
                // call Keycloak's real kcSanitize before handing markup to the layout.
                model.put("kcSanitize", (TemplateMethodModelEx) values -> values.get(0));
                for (String name : names) {
                    var scenario = new HashMap<>(model);
                    if (name.startsWith("event-") || name.equals("email-test.ftl")
                            || name.equals("email-verification-with-code.ftl")
                            || name.equals("workflow-notification.ftl")) scenario.remove("link");
                    render(custom, name, scenario, output.resolve(language).resolve(name.replace(".ftl", ".html")));
                    render(original, name, scenario, output.resolve(language).resolve("base").resolve(name.replace(".ftl", ".html")));
                }
                var unpersonalized = new HashMap<>(model);
                unpersonalized.remove("firstName");
                unpersonalized.remove("lastName");
                render(custom, "org-invite.ftl", unpersonalized, output.resolve(language).resolve("org-invite-unpersonalized.html"));
                var customWorkflow = new HashMap<>(model);
                customWorkflow.remove("link");
                customWorkflow.put("messageKey", "customMessage");
                render(custom, "workflow-notification.ftl", customWorkflow, output.resolve(language).resolve("workflow-custom.html"));
                var generalWorkflow = new HashMap<>(customWorkflow);
                generalWorkflow.put("subjectKey", "accountNotificationSubject");
                generalWorkflow.put("messageKey", "accountNotificationBody");
                render(custom, "workflow-notification.ftl", generalWorkflow, output.resolve(language).resolve("workflow-general.html"));
                var deleteWorkflow = new HashMap<>(customWorkflow);
                deleteWorkflow.put("subjectKey", "accountDeleteNotificationSubject");
                deleteWorkflow.put("messageKey", "accountDeleteNotificationBody");
                render(custom, "workflow-notification.ftl", deleteWorkflow, output.resolve(language).resolve("workflow-delete.html"));
                var previews = new ArrayList<>(names);
                previews.addAll(List.of("org-invite-unpersonalized.ftl", "workflow-custom.ftl",
                    "workflow-general.ftl", "workflow-delete.ftl"));
                for (String name : previews) {
                    index.append("<li><a href=\"").append(language).append("/")
                        .append(name.replace(".ftl", ".html")).append("\">").append(name).append("</a></li>");
                }
                index.append("</ul>");
            }
            Files.writeString(output.resolve("index.html"), index.append("</body></html>").toString());
            System.out.println("Rendered " + (names.size() * 2 + 8) + " Keycloak previews and base comparisons to " + output);
        }
    }

    private static void render(Configuration cfg, String name, Map<String, Object> model, Path file) throws Exception {
        var writer = new StringWriter();
        cfg.getTemplate(name).process(model, writer);
        Files.createDirectories(file.getParent());
        Files.writeString(file, writer.toString());
    }
}
