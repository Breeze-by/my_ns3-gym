"""Run preserved optimizer references under the new local-route input contract.

The stored sources/digests remain original. Only the explicit geometry input
at their old route calls changes; bounds, ordering and pricing remain frozen.
"""
import ast


def with_local_route_inputs(source):
    tree=ast.parse(source)
    for call in ast.walk(tree):
        if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name) or call.func.id!='plan_rally_leg':
            continue
        assert not any(keyword.arg=='local_map' for keyword in call.keywords)
        position=call.args[4]
        assert isinstance(position,ast.Subscript) and isinstance(position.value,ast.Attribute)
        assert position.value.attr=='robot_positions'
        robot=ast.unparse(position.slice)
        value=ast.parse('HeadquartersControl.delivered_return_maps(self).get('+robot+')',mode='eval').body
        call.keywords.append(ast.keyword(arg='local_map',value=value))
    return ast.fix_missing_locations(tree)
