{% if environment == "longtable" %}
{% include "latex_longtable.tpl" %}
{% else %}
{% include "latex_table.tpl" %}
{% endif %}
