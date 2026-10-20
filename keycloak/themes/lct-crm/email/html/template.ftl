<#-- Shared layout for the actual Keycloak 26.7.4 base email templates. -->
<#macro emailLayout title="" actionLabel="" actionUrl="" expiry="">
<#local templateName = .main_template_name?split("/")?last>
<#local titles = {
  "email-verification-with-code.ftl": "emailVerificationSubject",
  "email-update-confirmation.ftl": "emailUpdateConfirmationSubject",
  "identity-provider-link.ftl": "identityProviderLinkSubject",
  "org-invite.ftl": "orgInviteSubject",
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
<#if !title?has_content>
  <#local title = msg("lctAccountNotice")>
  <#if templateName == "identity-provider-link.ftl">
    <#local title = msg("identityProviderLinkSubject", identityProviderDisplayName)>
  <#elseif templateName == "org-invite.ftl">
    <#local title = msg("orgInviteSubject", organization.name)>
  <#elseif titles[templateName]??>
    <#local title = msg(titles[templateName])>
  </#if>
</#if>
<#if !actionUrl?has_content && link??><#local actionUrl = link></#if>
<!doctype html>
<html lang="${locale.language}" dir="${(ltr)?then('ltr','rtl')}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="x-apple-disable-message-reformatting">
  <title>${title}</title>
  <!--[if mso]><noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml></noscript><![endif]-->
  <style>
    table { border-collapse:collapse; mso-table-lspace:0; mso-table-rspace:0; }
    @media screen and (max-width:620px) { .pad { padding:26px 22px !important; } .outer { padding:16px 10px !important; } }
  </style>
</head>
<body style="margin:0;padding:0;background:#f4f4f7;-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="#f4f4f7" style="width:100%;background:#f4f4f7;">
    <tr><td class="outer" align="center" style="padding:36px 16px;">
      <!--[if mso]><table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0"><tr><td><![endif]-->
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px;font-family:Arial,Helvetica,sans-serif;color:#101828;">
        <tr><td class="pad" bgcolor="#4b006e" style="padding:28px 40px;background:#4b006e;border-top:5px solid #7700ff;">
          <p style="margin:0;color:#ffffff;font-size:21px;line-height:28px;font-weight:700;">${msg("lctBrandName")}</p>
          <p style="margin:5px 0 0;color:#eadbfa;font-size:13px;line-height:20px;">${msg("lctBrandSubtitle")}</p>
        </td></tr>
        <tr><td class="pad" bgcolor="#ffffff" style="padding:38px 40px 34px;background:#ffffff;">
          <h1 style="margin:0 0 22px;color:#1b1d29;font-size:26px;line-height:34px;font-weight:700;">${title}</h1>
          <div style="color:#344054;font-size:16px;line-height:26px;"><#nested></div>
          <#if actionUrl?has_content && actionLabel?has_content>
            <table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:26px 0 20px;"><tr><td bgcolor="#7700ff" align="center" style="background:#7700ff;border-radius:8px;mso-padding-alt:15px 24px;">
              <a href="${actionUrl?html}" style="display:inline-block;padding:15px 24px;border:1px solid #7700ff;border-radius:8px;background:#7700ff;color:#ffffff;text-decoration:none;font-size:15px;line-height:21px;font-weight:700;mso-padding-alt:0;">${actionLabel}</a>
            </td></tr></table>
            <p style="margin:0 0 18px;color:#667085;font-size:14px;line-height:22px;">${expiry?has_content?then(expiry,msg("lctLimitedTime"))}</p>
            <p style="margin:20px 0 0;color:#667085;font-size:12px;line-height:20px;word-break:break-all;">${msg("lctFallbackLink")}<br><a href="${actionUrl?html}" style="color:#5b00bf;text-decoration:underline;">${actionUrl?html}</a></p>
          </#if>
        </td></tr>
        <tr><td class="pad" bgcolor="#f8f6fc" style="padding:20px 40px;background:#f8f6fc;border-top:1px solid #e8e4ef;color:#667085;font-size:12px;line-height:19px;">${msg("lctAutomaticMessage")}</td></tr>
      </table>
      <!--[if mso]></td></tr></table><![endif]-->
    </td></tr>
  </table>
</body>
</html>
</#macro>
