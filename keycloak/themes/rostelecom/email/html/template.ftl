<#-- All base email templates import this macro. Keep their sanitized messages,
     text alternatives, subjects, required actions and expiration formatting. -->
<#macro emailLayout>
<#assign templateName = .main_template_name?split("/")?last>
<#assign subjects = {
  "executeActions.ftl": "executeActionsSubject",
  "password-reset.ftl": "passwordResetSubject",
  "email-verification.ftl": "emailVerificationSubject",
  "email-verification-with-code.ftl": "emailVerificationSubject",
  "email-update-confirmation.ftl": "emailUpdateConfirmationSubject",
  "identity-provider-link.ftl": "identityProviderLinkSubject",
  "org-invite.ftl": "orgInviteSubject",
  "verifiable-credential-offer.ftl": "verifiableCredentialOfferSubject",
  "email-test.ftl": "emailTestSubject",
  "event-login_error.ftl": "eventLoginErrorSubject",
  "event-update_password.ftl": "eventUpdatePasswordSubject",
  "event-update_totp.ftl": "eventUpdateTotpSubject",
  "event-remove_totp.ftl": "eventRemoveTotpSubject",
  "event-update_credential.ftl": "eventUpdateCredentialSubject",
  "event-remove_credential.ftl": "eventRemoveCredentialSubject",
  "event-user_disabled_by_temporary_lockout.ftl": "eventUserDisabledByTemporaryLockoutSubject",
  "event-user_disabled_by_permanent_lockout.ftl": "eventUserDisabledByPermanentLockoutSubject"
}>
<#assign heading = msg("rtkAccountNotification")>
<#if templateName == "workflow-notification.ftl">
  <#assign heading = msg(subjectKey, daysRemaining, reason)>
</#if>
<#if subjects[templateName]??>
  <#if templateName == "org-invite.ftl">
    <#assign heading = msg(subjects[templateName], organization.name)>
  <#elseif templateName == "identity-provider-link.ftl">
    <#assign heading = msg(subjects[templateName], identityProviderDisplayName)>
  <#else>
    <#assign heading = msg(subjects[templateName])>
  </#if>
</#if>
<#assign content><#nested></#assign>
<#-- Only add inline presentation to the markup sanitized by the base templates. -->
<#assign contentHtml = content?markup_string
  ?replace('<p>', '<p class="email-text" style="margin:0 0 16px;color:#344054;font-size:16px;line-height:26px;">')
  ?replace('<a ', '<a class="email-link" style="color:#7700ff;text-decoration:underline;word-break:break-all;" ')
  ?replace('<h2>', '<h2 class="email-heading" style="margin:0 0 20px;color:#101828;font-size:24px;line-height:32px;">')>
<#if templateName == "email-verification-with-code.ftl">
  <#assign contentHtml = contentHtml?replace('<b>', '<b class="email-heading" style="font-family:Consolas,monospace;font-size:28px;line-height:40px;letter-spacing:4px;color:#101828;">')>
</#if>
<!doctype html>
<html lang="${locale.language}" dir="${(ltr)?then('ltr','rtl')}" xmlns="http://www.w3.org/1999/xhtml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="x-apple-disable-message-reformatting">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>${heading}</title>
  <!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
  <style>
    :root { color-scheme: light dark; supported-color-schemes: light dark; }
    table { border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
    a[x-apple-data-detectors] { color: inherit !important; text-decoration: none !important; }
    @media screen and (max-width: 620px) {
      .email-outer { padding: 20px 12px !important; }
      .email-pad { padding: 24px !important; }
      .email-content { padding: 0 24px 28px !important; }
      .email-title { font-size: 24px !important; line-height: 32px !important; }
    }
    @media (prefers-color-scheme: dark) {
      .email-page { background-color: #16131e !important; }
      .email-card { background-color: #24202e !important; }
      .email-heading { color: #f5f3fa !important; }
      .email-text { color: #ded9e9 !important; }
      .email-muted { color: #b9b1c7 !important; }
      .email-line { border-color: #423a50 !important; }
      .email-link { color: #c6a1ff !important; }
    }
  </style>
</head>
<body class="email-page" bgcolor="#f4f4f7" style="margin:0;padding:0;width:100%;background-color:#f4f4f7;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="email-page" bgcolor="#f4f4f7" style="width:100%;background-color:#f4f4f7;">
    <tr><td align="center" class="email-outer" style="padding:40px 16px;">
      <!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;table-layout:fixed;font-family:'Rostelecom Basis','Basis Grotesque Pro',Arial,sans-serif;">
        <tr><td class="email-card email-pad" bgcolor="#ffffff" style="padding:32px 40px 28px;background-color:#ffffff;border-radius:18px 18px 0 0;">
          <#if url?? && url.resourcesUrl??>
            <img src="${url.resourcesUrl}/img/rostelecom-email.png" alt="Ростелеком — ИТ Школа" width="218" height="69" style="display:block;width:218px;max-width:100%;height:auto;border:0;border-radius:8px;background-color:#ffffff;color:#101828;font-family:Arial,sans-serif;font-size:18px;line-height:24px;">
          <#else>
            <p class="email-heading" style="margin:0;color:#101828;font-size:24px;line-height:30px;font-weight:700;">Ростелеком</p>
          </#if>
        </td></tr>
        <tr><td class="email-card email-pad email-content" bgcolor="#ffffff" style="padding:0 40px 36px;background-color:#ffffff;border-radius:0 0 18px 18px;word-wrap:break-word;overflow-wrap:anywhere;word-break:break-word;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;table-layout:fixed;">
            <tr><td class="email-line" style="border-top:1px solid #e7e5ed;padding:28px 0 0;">
              <p class="email-muted" style="margin:0 0 12px;color:#667085;font-size:12px;line-height:18px;letter-spacing:1px;">${msg("rtkAccountLabel")}</p>
              <#if templateName != "workflow-notification.ftl">
                <h1 class="email-heading email-title" style="margin:0 0 20px;color:#101828;font-size:28px;line-height:36px;font-weight:700;">${heading}</h1>
              </#if>
              ${contentHtml?no_esc}
            </td></tr>
            <#if link?? && link?has_content>
              <tr><td style="padding:12px 0 0;">
                <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                  <tr><td align="center" bgcolor="#7700ff" style="background-color:#7700ff;border-radius:10px;mso-padding-alt:14px 24px;">
                    <a href="${link}" style="display:inline-block;border:1px solid #7700ff;border-radius:10px;padding:13px 23px;color:#ffffff;background-color:#7700ff;font-size:16px;line-height:22px;font-weight:700;text-align:center;text-decoration:none;mso-padding-alt:0;">
                      <!--[if mso]><i style="mso-font-width:100%;mso-text-raise:21pt;" hidden>&#8202;</i><![endif]--><span style="mso-text-raise:10pt;">${msg("rtkContinue")}</span><!--[if mso]><i style="mso-font-width:100%;" hidden>&#8202;&#8203;</i><![endif]-->
                    </a>
                  </td></tr>
                </table>
              </td></tr>
              <tr><td class="email-muted" style="padding:20px 0 0;color:#667085;font-size:12px;line-height:20px;word-wrap:break-word;overflow-wrap:anywhere;word-break:break-all;">
                ${msg("rtkFallbackLink")}<br>
                <a class="email-link" href="${link}" style="color:#7700ff;text-decoration:underline;word-break:break-all;">${link}</a>
              </td></tr>
            </#if>
          </table>
        </td></tr>
        <tr><td class="email-muted" align="center" style="padding:24px 16px 0;color:#667085;font-size:12px;line-height:20px;">
          ${msg("rtkAutomaticMessage")}
        </td></tr>
      </table>
      <!--[if mso]></td></tr></table><![endif]-->
    </td></tr>
  </table>
</body>
</html>
</#macro>
