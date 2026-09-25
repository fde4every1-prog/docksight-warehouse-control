import React, { useState } from 'react';
import { useLocation } from 'wouter';
import { z } from 'zod';
import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Plus, Trash2, ArrowLeft, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Select } from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle, CardFooter } from '@/components/ui/card';
import { useCatalog, useCreateOrder } from '@/hooks/use-fulfillment';
import { FulfillmentNav } from './components/FulfillmentNav';
import { Skeleton } from '@/components/ui/skeleton';

const orderSchema = z.object({
  warehouse_id: z.string().min(1, "Warehouse is required"),
  priority: z.enum(['standard', 'high', 'urgent']),
  ship_by: z.string().min(1, "Ship-by date is required"),
  lines: z.array(z.object({
    sku: z.string().min(1, "SKU is required"),
    quantity: z.coerce.number().min(1, "Must be at least 1")
  })).min(1, "At least one order line is required")
});

export default function FulfillmentOrderForm() {
  const [, setLocation] = useLocation();
  const { data: catalog, isLoading: isCatalogLoading } = useCatalog();
  const createOrder = useCreateOrder();
  
  // Create a stable request ID for this session to prevent double submission
  const [requestId] = useState(() => crypto.randomUUID());

  const form = useForm<z.infer<typeof orderSchema>>({
    resolver: zodResolver(orderSchema),
    defaultValues: {
      warehouse_id: '',
      priority: 'standard',
      ship_by: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString().slice(0, 16),
      lines: [{ sku: '', quantity: 1 }]
    }
  });

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "lines"
  });

  const onSubmit = async (values: z.infer<typeof orderSchema>) => {
    try {
      const order = await createOrder.mutateAsync({
        ...values,
        ship_by: new Date(values.ship_by).toISOString(),
        request_id: requestId
      });
      setLocation(`/fulfillment/orders/${order.id}`);
    } catch (error) {
      console.error("Order creation failed", error);
      // handled by global error overlay or react query toast
    }
  };

  if (isCatalogLoading || !catalog) {
    return (
      <div className="p-6 space-y-6 max-w-4xl mx-auto">
        <FulfillmentNav active="orders" />
        <Skeleton className="h-[600px] w-full" />
      </div>
    );
  }

  // Since we want standard select with optgroups, we'll group by category
  const skusByCategory = catalog.skus.reduce((acc, sku) => {
    const cat = sku.temperature_class || 'Uncategorized';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(sku);
    return acc;
  }, {} as Record<string, Record<string, string>[]>);

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      <FulfillmentNav active="orders" />
      
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2 text-muted-foreground mb-2 cursor-pointer hover:text-foreground" onClick={() => setLocation('/fulfillment/orders')}>
            <ArrowLeft className="h-4 w-4" /> Back to Orders
          </div>
          <CardTitle>Create New Order</CardTitle>
          <CardDescription>Dispatch a simulated order to the fulfillment engine</CardDescription>
        </CardHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)}>
            <CardContent className="space-y-6">
              <div className="grid md:grid-cols-3 gap-6">
                <FormField
                  control={form.control}
                  name="warehouse_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Warehouse</FormLabel>
                      <FormControl>
                        <Select onChange={field.onChange} value={field.value || ""}>
                          <option value="" disabled>Select Warehouse</option>
                          {catalog.warehouses.map(w => (
                            <option key={w.warehouse_id} value={w.warehouse_id}>
                              {w.warehouse_id} ({w.region || 'Unknown'})
                            </option>
                          ))}
                        </Select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="priority"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Priority</FormLabel>
                      <FormControl>
                        <Select onChange={field.onChange} value={field.value || "standard"}>
                          <option value="standard">Standard</option>
                          <option value="high">High</option>
                          <option value="urgent">Urgent</option>
                        </Select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="ship_by"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Ship By</FormLabel>
                      <FormControl>
                        <Input type="datetime-local" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="border-t pt-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-base font-medium">Order Lines</h3>
                  <Button type="button" variant="outline" size="sm" onClick={() => append({ sku: '', quantity: 1 })}>
                    <Plus className="h-4 w-4 mr-2" /> Add Item
                  </Button>
                </div>
                
                <div className="space-y-4">
                  {fields.map((field, index) => (
                    <div key={field.id} className="flex items-start gap-4">
                      <FormField
                        control={form.control}
                        name={`lines.${index}.sku`}
                        render={({ field: skuField }) => (
                          <FormItem className="flex-1">
                            <FormLabel className="sr-only">Select SKU</FormLabel>
                            <FormControl>
                              <Select onChange={skuField.onChange} value={skuField.value || ""}>
                                <option value="" disabled>Search SKU...</option>
                                {Object.entries(skusByCategory).map(([cat, skus]) => (
                                  <optgroup key={cat} label={cat}>
                                    {skus.map(s => (
                                      <option key={s.sku} value={s.sku}>
                                        {s.sku} - {s.description}
                                      </option>
                                    ))}
                                  </optgroup>
                                ))}
                              </Select>
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      
                      <FormField
                        control={form.control}
                        name={`lines.${index}.quantity`}
                        render={({ field: qtyField }) => (
                          <FormItem className="w-24">
                            <FormLabel className="sr-only">Quantity</FormLabel>
                            <FormControl>
                              <Input type="number" min="1" {...qtyField} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      
                      <Button 
                        type="button" 
                        variant="ghost" 
                        size="icon" 
                        className="mt-1 text-destructive"
                        onClick={() => remove(index)}
                        disabled={fields.length === 1}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
            <CardFooter className="flex justify-between border-t bg-muted/20 py-4">
              <span className="text-xs text-muted-foreground font-mono">REQ: {requestId}</span>
              <Button type="submit" disabled={createOrder.isPending}>
                {createOrder.isPending ? 'Sending...' : 'Dispatch Order'}
                <Send className="ml-2 h-4 w-4" />
              </Button>
            </CardFooter>
          </form>
        </Form>
      </Card>
    </div>
  );
}
