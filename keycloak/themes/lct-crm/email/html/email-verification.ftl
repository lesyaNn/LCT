<#import "template.ftl" as layout>
<@layout.emailLayout title=msg("emailVerificationSubject") actionLabel=msg("lctVerifyEmail") actionUrl=link>
  <p style="margin:0 0 16px;"><#if ((user.firstName)!)?has_content>${msg("lctGreeting", user.firstName?html)}<#else>${msg("lctGreetingGeneric")}</#if></p>
  <p style="margin:0 0 16px;">${msg("lctVerifyIntro")}</p>
  <p style="margin:0;">${msg("lctIgnoreUnexpected")}</p>
</@layout.emailLayout>
