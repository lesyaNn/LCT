<#import "template.ftl" as layout>
<@layout.emailLayout title=msg("passwordResetSubject") actionLabel=msg("lctResetPassword") actionUrl=link>
  <p style="margin:0 0 16px;"><#if ((user.firstName)!)?has_content>${msg("lctGreeting", user.firstName?html)}<#else>${msg("lctGreetingGeneric")}</#if></p>
  <p style="margin:0 0 16px;">${msg("lctResetIntro")}</p>
  <p style="margin:0;">${msg("lctResetSafety")}</p>
</@layout.emailLayout>
