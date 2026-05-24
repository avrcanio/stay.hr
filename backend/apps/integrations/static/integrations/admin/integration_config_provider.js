(function ($) {
  $(function () {
    var $provider = $("#id_provider");
    if (!$provider.length) {
      return;
    }

    var initialProvider = $provider.val();
    $provider.on("change", function () {
      var nextProvider = $(this).val();
      if (!nextProvider || nextProvider === initialProvider) {
        return;
      }

      var $form = $(this).closest("form");
      if ($form.find('input[name="_continue"]').length === 0) {
        $("<input>", {
          type: "hidden",
          name: "_continue",
          value: "1",
        }).appendTo($form);
      }
      $form.trigger("submit");
    });
  });
})(django.jQuery);
