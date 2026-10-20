<#outputformat "plainText">
<#assign requiredActionsText><#if requiredActions??><#list requiredActions><#items as action>${msg("requiredAction.${action}")}<#sep>, </#sep></#items></#list></#if></#assign>
</#outputformat>
<#import "template.ftl" as layout>
<@layout.emailLayout title=msg("executeActionsSubject") actionLabel=msg("lctCompleteSetup") actionUrl=link>
  <p style="margin:0 0 16px;"><#if ((user.firstName)!)?has_content>${msg("lctGreeting", user.firstName?html)}<#else>${msg("lctGreetingGeneric")}</#if></p>
  <p style="margin:0 0 16px;">${msg("lctActionsIntro")}</p>
  <#if requiredActionsText?has_content><p style="margin:0 0 16px;">${msg("lctActionsList", requiredActionsText?html)}</p></#if>
  <p style="margin:0 0 16px;">${msg("lctActionsPrompt")}</p>
  <p style="margin:0;">${msg("lctIgnoreUnexpected")}</p>
</@layout.emailLayout>
